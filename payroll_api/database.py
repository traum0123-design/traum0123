from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from payroll_shared.settings import get_settings

# Load .env (개발 편의)
load_dotenv()


def get_database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    # 2) 로컬 개발 기본값: 레포 내 SQLite 파일
    here = Path(__file__).resolve().parent
    db_path = (here / ".." / "payroll_portal" / "app.db").resolve()
    return f"sqlite:///{db_path}"


SQLALCHEMY_DATABASE_URL = get_database_url()

engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db():
    from sqlalchemy.orm import Session
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
