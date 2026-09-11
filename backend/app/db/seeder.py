import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from app.db.database import get_session_factory
from app.db.models import MWBreakoutAlertModel
from app.db.repository import MWAlertRepository
from app.models.schemas import MWBreakoutAlert

logger = logging.getLogger(__name__)

# Candidate paths for the canonical historical W/M alerts store:
# 1. Bundled inside package (immune to /app/backend/data volume mount masking on Render)
# 2. In root backend/data/ directory
SEED_CANDIDATE_PATHS = [
    Path(__file__).resolve().parent / "seed_data" / "mw_breakout_alerts_store.json",
    Path(__file__).resolve().parents[2] / "data" / "mw_breakout_alerts_store.json",
]


def resolve_canonical_seed_file() -> Optional[Path]:
    """Finds the first existing canonical seed store path."""
    for candidate in SEED_CANDIDATE_PATHS:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_canonical_seed_alerts(seed_path: Optional[Path] = None) -> List[MWBreakoutAlert]:
    """
    Loads and validates canonical historical alerts from seed JSON.
    Normalizes legacy status strings to canonical outcomes.
    """
    path = seed_path or resolve_canonical_seed_file()
    if not path:
        logger.warning("[DB Seeder] No canonical seed JSON file found in candidate paths.")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            raw_alerts = data.get("alerts", [])
        elif isinstance(data, list):
            raw_alerts = data
        else:
            raw_alerts = []

        validated: List[MWBreakoutAlert] = []
        seen_keys = set()

        for item in raw_alerts:
            if not isinstance(item, dict):
                continue

            # Normalize legacy status representations
            status = item.get("status")
            if status in ["ACTIVE", "FALSE BREAKOUT", "FALSE_BREAKOUT"]:
                item["status"] = "TARGET OPEN"
            elif status == "INVALIDATED":
                item["status"] = "SL HIT"
            elif status == "TARGET_1_HIT":
                item["status"] = "TARGET 1 HIT"
            elif status == "TARGET_2_HIT":
                item["status"] = "TARGET 2 HIT"

            comp_key = (
                item.get("symbol"),
                item.get("timeframe"),
                item.get("pattern_type"),
                item.get("breakout_candle_timestamp"),
            )
            if comp_key in seen_keys:
                continue
            seen_keys.add(comp_key)

            try:
                validated.append(MWBreakoutAlert(**item))
            except Exception as parse_err:
                logger.debug(f"[DB Seeder] Skipping unparseable alert item: {parse_err}")
                continue

        return validated
    except Exception as e:
        logger.error(f"[DB Seeder] Error loading canonical seed file from {path}: {e}")
        return []


async def bootstrap_canonical_alerts(
    session_factory=None,
    seed_path: Optional[Path] = None,
) -> Dict[str, int]:
    """
    Idempotently and non-destructively bootstraps canonical historical W/M alerts into SQLite.

    Guarantees:
    1. Idempotent: Can be run repeatedly; duplicate runs insert 0 and skip all.
    2. Non-destructive: Never deletes or overwrites existing database records or modified statuses.
    3. Mount-safe: Resolves from bundled seed location immune to volume masking.
    4. Not hardcoded: Dynamically imports whatever is present in the canonical store.
    5. Deduplication: Strict natural key matching on (symbol, timeframe, pattern_type, breakout_candle_timestamp).
    """
    resolved_seed = seed_path or resolve_canonical_seed_file()
    alerts = load_canonical_seed_alerts(resolved_seed)
    if not alerts:
        logger.info("[DB Seeder] No canonical seed alerts to import.")
        return {"total_canonical": 0, "inserted": 0, "skipped": 0}

    # If /app/backend/data exists and is missing mw_breakout_alerts_store.json,
    # safely copy the seed file there so external diagnostics/tools can find it.
    try:
        data_dir = Path(__file__).resolve().parents[2] / "data"
        if data_dir.exists() and data_dir.is_dir() and resolved_seed:
            target_store = data_dir / "mw_breakout_alerts_store.json"
            if not target_store.exists() and resolved_seed != target_store:
                shutil.copy2(resolved_seed, target_store)
                logger.info(f"[DB Seeder] Synced canonical seed to data directory: {target_store}")
    except Exception as copy_err:
        logger.debug(f"[DB Seeder] Non-critical store sync error: {copy_err}")

    factory = session_factory or get_session_factory()
    inserted = 0
    skipped = 0

    async with factory() as session:
        repo = MWAlertRepository(session)

        for alert in alerts:
            # Check by physical breakout identity (symbol, tf, pattern, timestamp)
            existing = await repo.get_by_physical_identity(
                symbol=alert.symbol,
                timeframe=alert.timeframe,
                pattern_type=alert.pattern_type,
                breakout_candle_timestamp=alert.breakout_candle_timestamp,
            )

            if existing is not None:
                # Alert already exists in SQLite: preserve existing record and live outcomes!
                skipped += 1
                continue

            # Ensure alert_id doesn't collide with another event
            existing_by_id = await repo.get_by_id(alert.alert_id)
            alert_dict = alert.model_dump()
            if existing_by_id is not None:
                alert_dict["alert_id"] = f"{alert.alert_id}_{uuid.uuid4().hex[:8]}"

            new_model = MWBreakoutAlertModel(**alert_dict)
            session.add(new_model)
            inserted += 1

        if inserted > 0:
            await session.commit()
            logger.info(
                f"[DB Seeder] Canonical W/M alerts bootstrap complete: "
                f"inserted={inserted}, skipped={skipped}, total_canonical={len(alerts)}"
            )
        else:
            logger.info(
                f"[DB Seeder] Canonical W/M alerts bootstrap verified: "
                f"all {skipped} canonical records already present in database."
            )

    return {"total_canonical": len(alerts), "inserted": inserted, "skipped": skipped}
