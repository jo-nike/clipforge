"""
Secure database configuration and session management for ClipForge
Implements proper SQL injection protection and transaction management
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, Optional, Type

from core.config import settings
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text

logger = logging.getLogger(__name__)


# Database configuration
class Base(DeclarativeBase):
    """Base class for all database models"""

    pass


class DatabaseConfig:
    """Database configuration and setup"""

    def __init__(self) -> None:
        self.database_url = settings.database_url
        self.pool_size = settings.database_pool_size

        # Convert relative SQLite paths to absolute
        if self.database_url.startswith("sqlite:///") and not self.database_url.startswith(
            "sqlite:////"
        ):
            # Extract the path after sqlite:///
            db_path = self.database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                # Convert to absolute path relative to project root
                from pathlib import Path

                project_root = Path(
                    __file__
                ).parent.parent.parent  # Go up from infrastructure/database.py to project root
                abs_db_path = project_root / db_path
                self.database_url = f"sqlite:///{abs_db_path}"
                logger.info(f"Converted database URL to: {self.database_url}")

        # Configure engine based on database type
        if self.database_url.startswith("sqlite"):
            # SQLite configuration
            self.engine = create_engine(
                self.database_url,
                echo=False,  # Disable SQL query logging
                poolclass=StaticPool,
                connect_args={"check_same_thread": False, "timeout": 20},
            )
            # Enable foreign key constraints for SQLite
            event.listen(self.engine, "connect", self._set_sqlite_pragma)
        else:
            # PostgreSQL/MySQL configuration
            self.engine = create_engine(
                self.database_url,
                echo=False,  # Disable SQL query logging
                pool_size=self.pool_size,
                max_overflow=self.pool_size * 2,
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections every hour
            )

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        logger.info(f"Database configured: {self.database_url}")

    def _set_sqlite_pragma(self, dbapi_connection: Any, connection_record: Any) -> None:
        """Set SQLite pragmas for better performance and integrity"""
        cursor = dbapi_connection.cursor()
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        # Better synchronization
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    def create_tables(self) -> None:
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created/verified")

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()


# Global database configuration
db_config = DatabaseConfig()


# Updated Database Models with Security Constraints
class User(Base):
    """User model with security constraints"""

    __tablename__ = "users"

    user_id = Column(String(100), primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships with cascade delete
    clips = relationship("Clip", back_populates="user", cascade="all, delete-orphan")
    snapshots = relationship("Snapshot", back_populates="user", cascade="all, delete-orphan")
    edits = relationship("Edit", back_populates="user", cascade="all, delete-orphan")


class Clip(Base):
    """Clip model with validation"""

    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    duration: Mapped[Optional[int]] = mapped_column(Integer)

    # Metadata fields with length constraints
    show_name: Mapped[Optional[str]] = mapped_column(String(200))
    season_number: Mapped[Optional[int]] = mapped_column(Integer)
    episode_number: Mapped[Optional[int]] = mapped_column(Integer)
    original_timestamp: Mapped[Optional[str]] = mapped_column(String(50))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Status fields
    status: Mapped[str] = mapped_column(String(20), default="completed")
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    user = relationship("User", back_populates="clips")
    edits = relationship("Edit", back_populates="source_clip", cascade="all, delete-orphan")


class Edit(Base):
    """Edit model with constraints"""

    __tablename__ = "edits"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
    )
    source_clip_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("clips.id", ondelete="CASCADE"),
        index=True,
    )

    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    duration: Mapped[Optional[int]] = mapped_column(Integer)

    # Edit parameters with constraints
    start_time: Mapped[Optional[str]] = mapped_column(String(20))
    end_time: Mapped[Optional[str]] = mapped_column(String(20))
    quality: Mapped[Optional[str]] = mapped_column(String(20))
    format: Mapped[Optional[str]] = mapped_column(String(10))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Status fields
    status: Mapped[str] = mapped_column(String(20), default="completed")
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    user = relationship("User", back_populates="edits")
    source_clip = relationship("Clip", back_populates="edits")


class Snapshot(Base):
    """Snapshot model with constraints"""

    __tablename__ = "snapshots"

    id = Column(String(100), primary_key=True, index=True)
    user_id = Column(
        String(100),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    timestamp = Column(String(20))
    format = Column(String(10))
    quality = Column(String(20))

    # Media context with constraints
    media_title = Column(String(200))
    show_name = Column(String(200))
    season_number = Column(Integer)
    episode_number = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Status fields
    status = Column(String(20), default="completed", nullable=False)
    error_message = Column(Text)

    # Relationships
    user = relationship("User", back_populates="snapshots")


# Secure Session Management
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Secure context manager for database sessions with proper error handling

    Yields:
        Database session with automatic transaction management
    """
    session = db_config.get_session()
    try:
        yield session
        session.commit()
        logger.debug("Database transaction committed successfully")
    except Exception as e:
        session.rollback()
        logger.error(f"Database transaction rolled back due to error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions

    Yields:
        Database session for FastAPI dependency injection
    """
    session = db_config.get_session()
    try:
        yield session
    finally:
        session.close()


class SecureQueryBuilder:
    """Helper class for building secure database queries"""

    @staticmethod
    def build_user_filter(session: Session, user_id: str, model_class: Type[Any]) -> Any:
        """
        Build a secure user filter for queries

        Args:
            session: Database session
            user_id: User ID to filter by
            model_class: SQLAlchemy model class

        Returns:
            Query filter condition
        """
        # Validate user_id format (additional security check)
        if not user_id or len(user_id) > 100:
            raise ValueError("Invalid user ID")

        return model_class.user_id == user_id

    @staticmethod
    def build_pagination_query(query: Any, offset: int, limit: int) -> Any:
        """
        Build secure pagination query

        Args:
            query: Base query
            offset: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Paginated query
        """
        # Validate pagination parameters
        if offset < 0:
            offset = 0
        if limit <= 0 or limit > 100:
            limit = 20

        return query.offset(offset).limit(limit)

    @staticmethod
    def build_search_filter(column: Any, search_term: str) -> Any:
        """
        Build secure search filter with parameterized queries

        Args:
            column: Database column to search
            search_term: Search term (will be sanitized)

        Returns:
            Search filter condition
        """
        if not search_term or len(search_term) > 200:
            return None

        # Use parameterized query to prevent SQL injection
        sanitized_term = f"%{search_term.strip()}%"
        return column.ilike(sanitized_term)


def execute_raw_query(session: Session, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    Execute raw SQL query with parameter binding (SQL injection safe)

    Args:
        session: Database session
        query: SQL query with named parameters
        params: Query parameters

    Returns:
        Query result

    Example:
        result = execute_raw_query(
            session,
            "SELECT * FROM users WHERE user_id = :user_id",
            {"user_id": "123"}
        )
    """
    if params is None:
        params = {}

    try:
        result = session.execute(text(query), params)
        logger.debug(f"Executed raw query: {query} with params: {params}")
        return result
    except Exception as e:
        logger.error(f"Raw query execution failed: {e}")
        raise


def init_database() -> None:
    """Initialize database with proper error handling"""
    try:
        # Ensure database directory exists
        settings.create_required_directories()

        # Create tables
        db_config.create_tables()

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


# Health check function
def check_database_health() -> Dict[str, Any]:
    """
    Check database connectivity and health

    Returns:
        Health status dictionary
    """
    health_status = {
        "database": "unknown",
        "connection": False,
        "tables_exist": False,
        "error": None,
    }

    try:
        with get_db_session() as session:
            # Test basic connectivity
            session.execute(text("SELECT 1"))
            health_status["connection"] = True

            # Check if tables exist
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            if result.fetchone():
                health_status["tables_exist"] = True

            health_status["database"] = "healthy"

    except Exception as e:
        health_status["database"] = "unhealthy"
        health_status["error"] = str(e)
        logger.error(f"Database health check failed: {e}")

    return health_status
