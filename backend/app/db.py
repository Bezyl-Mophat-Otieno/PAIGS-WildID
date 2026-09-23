"""
Database engine/session setup.

DATABASE_URL defaults to a local SQLite file for prototyping, per CLAUDE.md
("PostgreSQL (SQLite acceptable for early prototype)"). Set PAIGS_DATABASE_URL
to point at Postgres in real deployments.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("PAIGS_DATABASE_URL", "sqlite:///./paigs.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
