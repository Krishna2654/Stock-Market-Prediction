import logging
from pathlib import Path
from typing import AsyncIterator, Optional
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def get_database_path() -> Path:
    """
    Resolves the canonical database path for persistent storage.
    If settings.DATABASE_PATH is relative, it is resolved inside backend/data/.
    """
    configured = Path(settings.DATABASE_PATH)
    if configured.is_absolute():
        configured.parent.mkdir(parents=True, exist_ok=True)
        return configured

    backend_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    backend_data_dir.mkdir(parents=True, exist_ok=True)
    return backend_data_dir / configured


def create_engine_and_sessionmaker(
    db_path: Optional[Path] = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    target_path = db_path or get_database_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{target_path.as_posix()}"

    eng = create_async_engine(
        db_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA busy_timeout=5000;")
        finally:
            cursor.close()

    session_factory = async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return eng, session_factory


# Default application-wide engine and sessionmaker
engine, async_session_factory = create_engine_and_sessionmaker()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns the current application-wide async session factory."""
    return async_session_factory


def set_engine_and_sessionmaker(
    new_engine: AsyncEngine,
    new_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sets or swaps the engine and session factory (e.g. for isolated test databases)."""
    global engine, async_session_factory
    engine = new_engine
    async_session_factory = new_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for yielding an asynchronous database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(target_engine: Optional[AsyncEngine] = None, seed_canonical: bool = False) -> None:
    """
    Safely creates all database tables and indexes if they do not already exist.
    Non-destructive; does not alter or delete existing data.
    If seed_canonical is True, safely and idempotently bootstraps canonical historical records.
    """
    import app.db.models  # Ensures all models are registered on Base.metadata
    eng = target_engine or engine
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[DB] SQLite database initialized in WAL mode successfully.")

    if seed_canonical:
        from app.db.seeder import bootstrap_canonical_alerts
        await bootstrap_canonical_alerts()
