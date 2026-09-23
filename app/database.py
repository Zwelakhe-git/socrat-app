import os
import time
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Retry logic: try to connect up to 10 times
def create_engine_with_retry(url, max_retries=10, delay=3):
    for attempt in range(max_retries):
        try:
            engine = create_engine(url, pool_pre_ping=True)
            # Test connection
            with engine.connect() as conn:
                print(f"✅ Successfully connected to database on attempt {attempt + 1}")
                return engine
        except OperationalError as e:
            print(f"⏳ DB not ready (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(delay)
    raise Exception("❌ Could not connect to database after multiple retries")

engine = create_engine_with_retry(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()