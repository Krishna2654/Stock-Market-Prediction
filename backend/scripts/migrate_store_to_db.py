import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.database import (
    async_session_factory,
    engine,
    get_database_path,
    init_db,
)
from app.db.repository import MigrationConflictError, MWAlertRepository
from app.models.schemas import MWBreakoutAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migration")

SOURCE_JSON = backend_dir / "data" / "mw_breakout_alerts_store.json"


def compute_file_sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_source_json() -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    if not SOURCE_JSON.exists():
        raise FileNotFoundError(f"Source JSON store not found at {SOURCE_JSON}")

    initial_hash = compute_file_sha256(SOURCE_JSON)
    with open(SOURCE_JSON, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict):
        raw_alerts = raw_data.get("alerts", [])
    elif isinstance(raw_data, list):
        raw_alerts = raw_data
    else:
        raw_alerts = []

    validated_alerts: List[MWBreakoutAlert] = []
    for item in raw_alerts:
        validated_alerts.append(MWBreakoutAlert(**item))

    w_count = sum(1 for a in validated_alerts if a.pattern_type == "W")
    m_count = sum(1 for a in validated_alerts if a.pattern_type == "M")
    timestamps = [a.breakout_candle_timestamp for a in validated_alerts if a.breakout_candle_timestamp]
    identities = [
        (a.symbol, a.timeframe, a.pattern_type, a.breakout_candle_timestamp)
        for a in validated_alerts
    ]

    metrics = {
        "count": len(validated_alerts),
        "w_count": w_count,
        "m_count": m_count,
        "unique_identities": len(set(identities)),
        "earliest": min(timestamps) if timestamps else None,
        "latest": max(timestamps) if timestamps else None,
    }
    return raw_alerts, metrics, initial_hash


async def run_migration_pass(alerts: List[MWBreakoutAlert]) -> Dict[str, int]:
    inserted = 0
    skipped = 0

    async with async_session_factory() as session:
        repo = MWAlertRepository(session)
        for alert in alerts:
            action, _ = await repo.migrate_single_alert_safe(alert)
            if action == "INSERTED":
                inserted += 1
            elif action == "SKIPPED":
                skipped += 1
        await session.commit()

    return {"inserted": inserted, "skipped": skipped}


async def verify_field_parity(alerts: List[MWBreakoutAlert]) -> Tuple[bool, List[str]]:
    critical_fields = [
        "alert_id",
        "symbol",
        "timeframe",
        "pattern_type",
        "s1_price",
        "s1_timestamp",
        "s2_price",
        "s2_timestamp",
        "neckline_price",
        "neckline_timestamp",
        "pattern_height",
        "breakout_candle_timestamp",
        "breakout_open",
        "breakout_high",
        "breakout_low",
        "breakout_close",
        "measured_target",
        "target_2",
        "invalidation_level",
        "status",
        "outcome_timestamp",
        "quality_score",
    ]

    errors = []
    async with async_session_factory() as session:
        repo = MWAlertRepository(session)
        for a in alerts:
            model = await repo.get_by_physical_identity(
                symbol=a.symbol,
                timeframe=a.timeframe,
                pattern_type=a.pattern_type,
                breakout_candle_timestamp=a.breakout_candle_timestamp,
            )
            if not model:
                errors.append(f"Missing in DB: {a.alert_id}")
                continue

            db_dict = model.to_dict()
            json_dict = a.model_dump()
            for cf in critical_fields:
                j_val = json_dict.get(cf)
                d_val = db_dict.get(cf)
                if isinstance(j_val, float) and isinstance(d_val, (float, int)):
                    if abs(j_val - float(d_val)) > 1e-5:
                        errors.append(f"Value mismatch in {a.alert_id} for {cf}: JSON={j_val}, DB={d_val}")
                elif j_val != d_val:
                    errors.append(f"Value mismatch in {a.alert_id} for {cf}: JSON={j_val}, DB={d_val}")

    return len(errors) == 0, errors


async def main():
    logger.info("=" * 70)
    logger.info("STAGE 1: PERSISTENT HISTORICAL W/M DATABASE MIGRATION")
    logger.info("=" * 70)

    # 1. Inspect Source JSON
    raw_json_items, src_metrics, initial_hash = load_source_json()
    validated_alerts = [MWBreakoutAlert(**item) for item in raw_json_items]

    logger.info(f"Source JSON Path:             {SOURCE_JSON}")
    logger.info(f"Source SHA-256:               {initial_hash}")
    logger.info(f"Source Total Alerts:          {src_metrics['count']}")
    logger.info(f"Source W Patterns:            {src_metrics['w_count']}")
    logger.info(f"Source M Patterns:            {src_metrics['m_count']}")
    logger.info(f"Source Unique Identities:     {src_metrics['unique_identities']}")
    logger.info(f"Source Earliest Timestamp:    {src_metrics['earliest']}")
    logger.info(f"Source Latest Timestamp:      {src_metrics['latest']}")

    # 2. Initialize Database & Tables
    db_path = get_database_path()
    logger.info(f"Target Database Path:         {db_path}")
    await init_db()
    logger.info("Database initialized successfully with WAL mode enabled.")

    # 3. Execute Migration Pass 1
    logger.info("-" * 70)
    logger.info("Running Migration Pass 1 (Initial Transfer)...")
    res1 = await run_migration_pass(validated_alerts)
    logger.info(f"Pass 1 Result: Inserted={res1['inserted']}, Skipped={res1['skipped']}")

    # 4. Database Metrics Verification
    async with async_session_factory() as session:
        repo = MWAlertRepository(session)
        db_metrics = await repo.get_metrics()

    logger.info("-" * 70)
    logger.info("DATABASE POST-MIGRATION METRICS:")
    logger.info(f"DB Total Alerts:              {db_metrics['total_count']}")
    logger.info(f"DB W Patterns:                {db_metrics['w_count']}")
    logger.info(f"DB M Patterns:                {db_metrics['m_count']}")
    logger.info(f"DB Unique Physical Identities:{db_metrics['unique_identities']}")
    logger.info(f"DB Duplicate Identities:      {db_metrics['duplicate_identities']}")
    logger.info(f"DB Earliest Timestamp:        {db_metrics['earliest_timestamp']}")
    logger.info(f"DB Latest Timestamp:          {db_metrics['latest_timestamp']}")

    # Check metrics parity
    if db_metrics["total_count"] != src_metrics["count"]:
        raise ValueError(f"COUNT MISMATCH: JSON={src_metrics['count']} vs DB={db_metrics['total_count']}")
    if db_metrics["w_count"] != src_metrics["w_count"]:
        raise ValueError(f"W COUNT MISMATCH: JSON={src_metrics['w_count']} vs DB={db_metrics['w_count']}")
    if db_metrics["m_count"] != src_metrics["m_count"]:
        raise ValueError(f"M COUNT MISMATCH: JSON={src_metrics['m_count']} vs DB={db_metrics['m_count']}")
    if db_metrics["unique_identities"] != src_metrics["unique_identities"]:
        raise ValueError("UNIQUE IDENTITIES MISMATCH!")
    if db_metrics["duplicate_identities"] != 0:
        raise ValueError(f"DUPLICATES DETECTED IN DB: {db_metrics['duplicate_identities']}")

    # 5. Field-by-Field Lossless Verification
    logger.info("-" * 70)
    logger.info("Running Field-by-Field Parity Verification for all records...")
    is_parity_clean, parity_errors = await verify_field_parity(validated_alerts)
    if not is_parity_clean:
        logger.error(f"Field parity failures detected ({len(parity_errors)}):")
        for err in parity_errors[:10]:
            logger.error(f"  - {err}")
        raise ValueError("FIELD PARITY VERIFICATION FAILED!")
    logger.info("Field parity verified: 100% of stored attributes match exactly.")

    # 6. Migration Idempotency Test (Pass 2)
    logger.info("-" * 70)
    logger.info("Running Migration Pass 2 (Idempotency Test)...")
    res2 = await run_migration_pass(validated_alerts)
    logger.info(f"Pass 2 Result: Inserted={res2['inserted']}, Skipped={res2['skipped']}")

    if res2["inserted"] != 0:
        raise ValueError(f"IDEMPOTENCY FAILURE: Pass 2 inserted {res2['inserted']} records instead of 0!")
    if res2["skipped"] != src_metrics["count"]:
        raise ValueError(f"IDEMPOTENCY FAILURE: Pass 2 skipped {res2['skipped']} records instead of {src_metrics['count']}!")

    async with async_session_factory() as session:
        repo = MWAlertRepository(session)
        db_metrics_pass2 = await repo.get_metrics()
    if db_metrics_pass2["total_count"] != src_metrics["count"]:
        raise ValueError(f"COUNT CHANGED AFTER PASS 2: {db_metrics_pass2['total_count']}")

    logger.info("Migration idempotency verified: 0 duplicates created, all records safely skipped.")

    # 7. Source JSON Integrity Verification
    final_hash = compute_file_sha256(SOURCE_JSON)
    if final_hash != initial_hash:
        raise ValueError("FATAL ERROR: Source JSON file was modified during migration!")
    logger.info(f"Source JSON integrity verified: SHA-256 unchanged ({final_hash}).")

    logger.info("=" * 70)
    logger.info("STAGE 1 COMPLETE — DATABASE MIGRATION VERIFIED SUCCESSFULLY")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
