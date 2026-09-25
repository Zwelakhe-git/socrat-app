import os
import time
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from . import models
from .auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, oauth2_scheme
)
from .podcast import generate_podcast_script, generate_podcast_audio
from .cache import cache_get, cache_set, cache_delete, get_cached_history
from .tasks import generate_podcast_task

load_dotenv()

# Init DB with retry
def init_db():
    for attempt in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ Database tables initialized")
            return
        except Exception as e:
            print(f"⏳ Waiting for DB (attempt {attempt + 1}): {e}")
            time.sleep(3)
    raise Exception("❌ Could not init DB")

init_db()

app = FastAPI(title="Socrat API")
app.mount("/static", StaticFiles(directory="static"), name="static")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

SYSTEM_PROMPT = """You are a brilliant, engaging, and concise tutor. 
Your goal is to answer the student's questions clearly, using relatable analogies. 
Keep your answers relatively short so they are easy to listen to later. 
Avoid overly dense academic jargon unless asked."""

# ---------- Schemas ----------
class UserRegister(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    user_message: str

class SessionCreateResponse(BaseModel):
    session_id: int
    title: str

class SessionDetail(BaseModel):
    id: int
    title: str
    podcast_url: str | None
    podcast_status: str
    created_at: str

    class Config:
        from_attributes = True

# ---------- Health ----------
@app.get("/")
def read_root():
    return {"message": "Socrat API is running!"}

# ---------- AUTH ENDPOINTS ----------
@app.post("/api/auth/register")
def register(data: UserRegister, db: Session = Depends(get_db)):
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    
    existing = db.query(models.User).filter(models.User.username == data.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")

    user = models.User(
        username=data.username,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username}

@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")

    token = create_access_token(user.id, user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username}

@app.get("/api/auth/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username}

# ---------- SESSION ENDPOINTS ----------
@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_session(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    new_session = models.ChatSession(user_id=current_user.id, title="Новый чат")
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"session_id": new_session.id, "title": new_session.title}

@app.get("/api/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == current_user.id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "podcast_url": s.podcast_url,
            "podcast_status": s.podcast_status,
            "created_at": s.created_at.isoformat()
        }
        for s in sessions
    ]

@app.get("/api/sessions/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")

    messages = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).order_by(models.Message.created_at).all()

    return {
        "id": session.id,
        "title": session.title,
        "podcast_url": session.podcast_url,
        "podcast_status": session.podcast_status,
        "created_at": session.created_at.isoformat(),
        "messages": [{"role": m.role, "content": m.content} for m in messages]
    }

# ---------- CHAT ENDPOINT (with Redis caching) ----------
@app.post("/api/sessions/{session_id}/chat")
def chat_with_tutor(
    session_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # ---- Try Redis cache first ----
    history = get_cached_history(session_id)
    if history is None:
        # Cache miss: load from DB and populate cache
        db_history = db.query(models.Message).filter(
            models.Message.session_id == session_id
        ).order_by(models.Message.created_at).all()
        history = [{"role": m.role, "content": m.content} for m in db_history]
        cache_set(f"history:{session_id}", history, ttl=3600)
        print(f"🔵 Cache MISS for session {session_id}")
    else:
        print(f"🟢 Cache HIT for session {session_id}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": request.user_message})

    # Save user message
    user_msg = models.Message(session_id=session_id, role="user", content=request.user_message)
    db.add(user_msg)
    db.commit()

    # Auto-set title from first user message
    if session.title == "Новый чат":
        session.title = request.user_message[:50]
        db.commit()

    # Call DeepSeek
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            stream=False
        )
        ai_response = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(500, f"DeepSeek error: {str(e)}")

    # Save AI response
    ai_msg = models.Message(session_id=session_id, role="assistant", content=ai_response)
    db.add(ai_msg)
    db.commit()

    # Invalidate cache — next request will reload from DB
    cache_delete(f"history:{session_id}")

    return {"status": "success", "ai_response": ai_response}

# ---------- PODCAST ENDPOINT ----------
@app.post("/api/sessions/{session_id}/podcast")
def start_podcast(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Dispatch podcast generation to Celery. Returns immediately.
    """
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Already ready? Just return it.
    if session.podcast_status == "ready" and session.podcast_url:
        return {
            "status": "ready",
            "podcast_url": session.podcast_url,
            "message": "Podcast already exists"
        }

    # Already generating? Don't double-dispatch.
    if session.podcast_status == "generating":
        return {
            "status": "generating",
            "message": "Podcast is already being generated"
        }

    # Check we have enough messages
    msg_count = db.query(models.Message).filter(
        models.Message.session_id == session_id
    ).count()
    if msg_count < 2:
        raise HTTPException(400, "Not enough messages to generate podcast")

    # Dispatch task
    session.podcast_status = "generating"
    db.commit()

    task = generate_podcast_task.delay(session_id)
    print(f"🚀 Dispatched task {task.id} for session {session_id}")

    return {
        "status": "generating",
        "task_id": task.id
    }


@app.get("/api/sessions/{session_id}/podcast/status")
def get_podcast_status(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Frontend polls this to check podcast progress.
    """
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "status": session.podcast_status,   # none | generating | ready | failed
        "podcast_url": session.podcast_url,
    }