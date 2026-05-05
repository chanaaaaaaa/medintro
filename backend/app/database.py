from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _engine_kwargs():
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        # FastAPI/Uvicorn 可能跨執行緒使用連線時需關閉 SQLite 的同執行緒限制
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
