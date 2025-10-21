from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from core.db import fastapi_session, get_engine, get_sessionmaker

# Load .env (개발 편의)
load_dotenv()

engine = get_engine()
SessionLocal: sessionmaker = get_sessionmaker()


def get_db():
    yield from fastapi_session()
