from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
def database_url(config=settings):
    url = make_url(config.database_url)
    if config.database_password_file:
        if url.get_backend_name() != 'postgresql':
            raise ValueError('Database password file requires PostgreSQL')
        password = Path(config.database_password_file).read_text().rstrip('\r\n')
        if not password:
            raise ValueError('Database password file is empty')
        url = url.set(password=password)
    return url

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(database_url(), connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
