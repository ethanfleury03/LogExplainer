"""
Database models for Error Debug feature.

SQLAlchemy models for machines and machine_index_versions tables.
Supports both Postgres (via DATABASE_URL) and SQLite fallback.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import json
import uuid

Base = declarative_base()


# UUID type that works with both Postgres and SQLite
class GUID(TypeDecorator):
    """Platform-independent GUID type."""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PostgresUUID())
        else:
            return dialect.type_descriptor(String(36))
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            return str(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            return value


# JSON type that works with both Postgres and SQLite
class JSONType(TypeDecorator):
    """Platform-independent JSON type."""
    impl = Text
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(Text())
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


class Machine(Base):
    """Machine model - represents a printer machine."""
    __tablename__ = 'error_debug_machines'
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    display_name = Column(String(255), unique=True, nullable=False, index=True)
    printer_model = Column(String(255), nullable=False)
    printing_type = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    active_version_id = Column(GUID(), ForeignKey('error_debug_machine_index_versions.id'), nullable=True)
    
    # Relationship
    # Explicitly specify foreign_keys to avoid ambiguity (machine_id is the FK, not active_version_id)
    versions = relationship(
        'MachineIndexVersion',
        back_populates='machine',
        foreign_keys='MachineIndexVersion.machine_id',
        cascade='all, delete-orphan'
    )
    active_version = relationship(
        'MachineIndexVersion',
        foreign_keys=[active_version_id],
        remote_side='MachineIndexVersion.id',
        post_update=True
    )


class MachineIndexVersion(Base):
    """Machine index version model - represents an uploaded index file."""
    __tablename__ = 'error_debug_machine_index_versions'
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    machine_id = Column(GUID(), ForeignKey('error_debug_machines.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # Upload time
    indexed_at = Column(DateTime, nullable=False)  # From index JSON created_at
    schema_version = Column(String(50), nullable=False)
    gcs_bucket = Column(String(255), nullable=True)  # Nullable for local storage
    gcs_object = Column(String(500), nullable=False)  # Object path or local storage path
    file_sha256 = Column(String(64), nullable=False, index=True)
    total_chunks = Column(Integer, nullable=False)
    total_errors = Column(Integer, nullable=False)
    stats_json = Column(JSONType(), nullable=True)  # Store stats blob as JSON
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    
    # Relationship
    machine = relationship('Machine', back_populates='versions', foreign_keys=[machine_id])

