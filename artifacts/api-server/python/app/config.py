import os
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required to start the API.")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def jwt_secret() -> str:
    value = os.environ.get("SESSION_SECRET")
    if not value:
        raise RuntimeError("SESSION_SECRET is required to sign authentication tokens.")
    if len(value) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters.")
    return value


DATABASE_URL = _database_url()
ACCESS_TOKEN_TTL = timedelta(hours=12)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
