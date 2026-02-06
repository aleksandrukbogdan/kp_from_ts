# database.py
"""
Database layer for user file history.
Uses SQLite for simplicity, designed for easy migration to PostgreSQL.
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/user_files.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Create data directory for SQLite
if IS_SQLITE:
    os.makedirs("./data", exist_ok=True)

# SQLAlchemy setup
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserFile(Base):
    """Model for storing user file upload history."""
    __tablename__ = "user_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), nullable=False, index=True)
    workflow_id = Column(String(100), unique=True, nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="PROCESSING")
    
    # Cached results for quick display (avoid querying Temporal for history)
    extracted_data_cache = Column(JSON, nullable=True)
    final_proposal_cache = Column(Text, nullable=True)


def init_db():
    """Create database tables."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db():
    """Database session context manager."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_user_file(
    username: str,
    workflow_id: str,
    original_filename: str
) -> UserFile:
    """Save new file upload record."""
    with get_db() as db:
        user_file = UserFile(
            username=username,
            workflow_id=workflow_id,
            original_filename=original_filename,
            status="PROCESSING"
        )
        db.add(user_file)
        db.commit()
        db.refresh(user_file)
        return user_file


def update_file_status(
    workflow_id: str,
    status: str,
    extracted_data: Optional[dict] = None,
    final_proposal: Optional[str] = None
) -> Optional[UserFile]:
    """Update file status and cache results."""
    with get_db() as db:
        user_file = db.query(UserFile).filter(
            UserFile.workflow_id == workflow_id
        ).first()
        
        if user_file:
            user_file.status = status
            if extracted_data is not None:
                user_file.extracted_data_cache = extracted_data
            if final_proposal is not None:
                user_file.final_proposal_cache = final_proposal
            db.commit()
            db.refresh(user_file)
        return user_file


def get_user_files(username: str) -> List[dict]:
    """Get all files for a user, ordered by upload date (newest first)."""
    with get_db() as db:
        files = db.query(UserFile).filter(
            UserFile.username == username
        ).order_by(UserFile.uploaded_at.desc()).all()
        
        return [
            {
                "id": f.id,
                "workflow_id": f.workflow_id,
                "filename": f.original_filename,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "status": f.status,
                "has_extracted_data": f.extracted_data_cache is not None,
                "has_proposal": f.final_proposal_cache is not None
            }
            for f in files
        ]


def get_file_by_workflow_id(workflow_id: str) -> Optional[dict]:
    """Get file details by workflow ID."""
    with get_db() as db:
        f = db.query(UserFile).filter(
            UserFile.workflow_id == workflow_id
        ).first()
        
        if not f:
            return None
        
        return {
            "id": f.id,
            "username": f.username,
            "workflow_id": f.workflow_id,
            "filename": f.original_filename,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
            "status": f.status,
            "extracted_data": f.extracted_data_cache,
            "final_proposal": f.final_proposal_cache
        }


def get_file_owner(workflow_id: str) -> Optional[str]:
    """Get username who owns the workflow."""
    with get_db() as db:
        f = db.query(UserFile).filter(
            UserFile.workflow_id == workflow_id
        ).first()
        return f.username if f else None


# Initialize database on import
init_db()
