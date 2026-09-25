import os
import asyncio
from datetime import datetime
from .celery_app import celery_app
from .database import SessionLocal
from . import models
from .podcast import generate_podcast_script, generate_podcast_audio


@celery_app.task(name="generate_podcast_task", bind=True)
def generate_podcast_task(self, session_id: int):
    """
    Background task: generate a podcast script + audio for a session.
    """
    print(f"🎬 [Task {self.request.id}] Starting podcast for session {session_id}")
    db = SessionLocal()

    try:
        session = db.query(models.ChatSession).filter(
            models.ChatSession.id == session_id
        ).first()

        if not session:
            print(f"❌ Session {session_id} not found")
            return {"status": "failed", "reason": "session not found"}

        # Mark as generating
        session.podcast_status = "generating"
        db.commit()

        # Fetch chat history
        history = db.query(models.Message).filter(
            models.Message.session_id == session_id
        ).order_by(models.Message.created_at).all()

        if len(history) < 2:
            session.podcast_status = "failed"
            db.commit()
            return {"status": "failed", "reason": "not enough messages"}

        chat_history = [{"role": m.role, "content": m.content} for m in history]

        # Step 1: Generate script (sync API call)
        print(f"📝 [Task {self.request.id}] Generating script...")
        script = generate_podcast_script(chat_history)

        # Step 2: Generate audio (async, run in event loop)
        print(f"🔊 [Task {self.request.id}] Synthesizing audio...")
        filename = f"podcast_session_{session_id}.mp3"
        output_path = f"/app/static/podcasts/{filename}"

        # edge-tts is async — run it in a fresh event loop inside the worker
        asyncio.run(generate_podcast_audio(script, output_path))

        # Step 3: Update DB
        session.podcast_url = f"/static/podcasts/{filename}"
        session.podcast_status = "ready"
        db.commit()

        print(f"✅ [Task {self.request.id}] Podcast ready: {session.podcast_url}")
        return {
            "status": "ready",
            "podcast_url": session.podcast_url,
            "task_id": self.request.id,
        }

    except Exception as e:
        print(f"❌ [Task {self.request.id}] Failed: {e}")
        try:
            session = db.query(models.ChatSession).filter(
                models.ChatSession.id == session_id
            ).first()
            if session:
                session.podcast_status = "failed"
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()