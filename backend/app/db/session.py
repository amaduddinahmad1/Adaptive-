"""
app/db/session.py

Database engine and session management. DATABASE_URL is read via plain
os.getenv() -- not pydantic-settings -- for consistency with how
GEMINI_API_KEY/GEMINI_MODEL are already read elsewhere in this codebase
(gemini_provider.py, cv_parser.py, jd_parser.py). Mirrors that same
lazy-init pattern too: no connection is attempted at import time, and a
clear error is raised only when a session is actually requested without
DATABASE_URL set.
"""
import os
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Set it in .env (see .env.example)."
            )
        _engine = create_engine(database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a Session, always closed after the request."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
