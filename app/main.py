import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from . import models

load_dotenv()

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Socrat API")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

SYSTEM_PROMPT = """You are a brilliant, engaging, and concise tutor. 
Your goal is to answer the student's questions clearly, using relatable analogies. 
Keep your answers relatively short so they are easy to listen to later. 
Avoid overly dense academic jargon unless asked."""

class ChatRequest(BaseModel):
    user_message: str

class SessionCreateResponse(BaseModel):
    session_id: int
    title: str

@app.get("/")
def read_root():
    return {"message": "Socrat API is running!"}

@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_session(db: Session = Depends(get_db)):
    new_session = models.ChatSession(title="New Chat")
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"session_id": new_session.id, "title": new_session.title}

@app.post("/api/sessions/{session_id}/chat")
def chat_with_tutor(session_id: int, request: ChatRequest, db: Session = Depends(get_db)):
    # 1. Fetch the session
    session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 2. Fetch previous messages from DB to build context
    history = db.query(models.Message).filter(models.Message.session_id == session_id).order_by(models.Message.created_at).all()
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.user_message})

    # 3. Save user message to DB
    user_msg = models.Message(session_id=session_id, role="user", content=request.user_message)
    db.add(user_msg)
    db.commit()

    # 4. Call DeepSeek
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            stream=False
        )
        ai_response = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DeepSeek error: {str(e)}")

    # 5. Save AI response to DB
    ai_msg = models.Message(session_id=session_id, role="assistant", content=ai_response)
    db.add(ai_msg)
    db.commit()

    return {
        "status": "success",
        "ai_response": ai_response
    }