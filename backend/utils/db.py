"""
Database initialization and connection management.

Supports both Postgres (via DATABASE_URL) and SQLite fallback for local development.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Import models to ensure they're registered
from backend.models.error_debug_models import Base

# Get database URL
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Use provided DATABASE_URL (Postgres)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    # SQLite fallback for local development
    # Use absolute path for stability regardless of working directory
    # Windows-compatible: Path handles / correctly, convert to string for SQLite URI
    from pathlib import Path
    repo_root = Path(__file__).parent.parent.parent.resolve()
    sqlite_path = repo_root / 'dev_storage' / 'error_debug.db'
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    # Convert Path to string, use forward slashes for SQLite URI (works on Windows too)
    sqlite_uri = f'sqlite:///{str(sqlite_path).replace(chr(92), "/")}'
    engine = create_engine(
        sqlite_uri,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database - create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

