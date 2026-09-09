import asyncio
from pathlib import Path
import pytest

from app.alerts import mw_breakout_engine
from app.db.database import (
    create_engine_and_sessionmaker,
    init_db,
    set_engine_and_sessionmaker,
    engine as prod_engine,
    async_session_factory as prod_factory,
)


@pytest.fixture(autouse=True)
def isolate_global_mw_storage(tmp_path, monkeypatch):
    """
    Globally isolates mw_breakout_engine.STORAGE_FILE to a temporary location
    during test runs to ensure backend/data/mw_breakout_alerts_store.json
    remains strictly read-only and is never modified by any test.
    """
    temp_store = tmp_path / "mw_test_alerts_store.json"
    monkeypatch.setattr("app.alerts.mw_breakout_engine.STORAGE_FILE", temp_store)


@pytest.fixture(autouse=True)
def isolate_global_test_db(tmp_path, monkeypatch, request):
    """
    Globally isolates the SQLite database to a temporary location for test runs,
    ensuring that backend/data/market_analyzer.db remains pristine and is never
    contaminated by test writes.
    Tests marked with @pytest.mark.production_db access the real database directly.
    """
    if "production_db" in request.keywords:
        yield
        return

    test_db_path = tmp_path / "test_market_analyzer.db"
    monkeypatch.setattr("app.core.config.settings.DATABASE_PATH", str(test_db_path))
    test_eng, test_factory = create_engine_and_sessionmaker(test_db_path)
    asyncio.run(init_db(test_eng))

    old_engine = prod_engine
    old_factory = prod_factory
    set_engine_and_sessionmaker(test_eng, test_factory)

    yield

    set_engine_and_sessionmaker(old_engine, old_factory)
    asyncio.run(test_eng.dispose())
