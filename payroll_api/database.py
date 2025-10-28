from dotenv import load_dotenv

from core.db import fastapi_session

# Load .env (개발 편의)
load_dotenv()


def get_db():
    yield from fastapi_session()
