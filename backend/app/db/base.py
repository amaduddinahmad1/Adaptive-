"""
app/db/base.py

Single declarative base shared by every ORM model. Kept separate from
session.py (engine/session creation) so Alembic's env.py can import just
Base.metadata without triggering an actual database connection.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
