"""
Migration Script: Migrate historical W/M Target 2 values in mw_breakout_alerts_store.json
from legacy 2.0x calculations to canonical 1.618x pattern height formula.

Usage:
    python backend/scripts/migrate_wm_t2_to_1618.py [--include-outliers] [--dry-run]
"""

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

DEFAULT_STORE_PATH = Path("backend/data/mw_breakout_alerts_store.json")
BACKUP_PATH = Path("backend/data/mw_breakout_alerts_store.backup_before_t2_migration.json")

def calculate_canonical_targets(pattern_type: str, neckline: float, height: float) -> Tuple[float, float]:
    if pattern_type == "W":
        t1 = round(neckline + height, 2)
        t2 = round(neckline + 1.618 * height, 2)
    elif pattern_type == "M":
        t1 = round(neckline - height, 2)
        t2 = round(neckline - 1.618 * height, 2)
    else:
        raise ValueError(f"Unknown pattern_type: {pattern_type}")
    return t1, t2

def calculate_old_20_target(pattern_type: str, neckline: float, height: float) -> float:
    if pattern_type == "W":
        return round(neckline + 2.0 * height, 2)
    elif pattern_type == "M":
        return round(neckline - 2.0 * height, 2)
    else:
        raise ValueError(f"Unknown pattern_type: {pattern_type}")

def run_migration(
    store_path: Path = DEFAULT_STORE_PATH,
    backup_path: Path = BACKUP_PATH,
    include_outliers: bool = False,
    dry_run: bool = False,
    tolerance: float = 0.05
) -> Dict[str, Any]:
    if not store_path.exists():
        raise FileNotFoundError(f"Store file not found: {store_path}")

    # 1. Create backup if not already present
    if not backup_path.exists():
        shutil.copy2(store_path, backup_path)
        print(f"[BACKUP] Created backup at: {backup_path} ({os.path.getsize(backup_path)} bytes)")
    else:
        print(f"[BACKUP] Verified existing backup at: {backup_path} ({os.path.getsize(backup_path)} bytes)")

    # 2. Load store data
    with open(store_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    is_dict = isinstance(data, dict)
    alerts: List[Dict[str, Any]] = data.get("alerts", []) if is_dict else data
    total_before = len(alerts)

    # 3. Classify records
    already_correct = []
    confirmed_20 = []
    outliers = []

    for idx, alert in enumerate(alerts):
        pt = alert.get("pattern_type")
        n = alert.get("neckline_price")
        h = alert.get("pattern_height")
        t2 = alert.get("target_2")

        if pt not in ["W", "M"] or n is None or h is None:
            continue

        canonical_t1, canonical_t2 = calculate_canonical_targets(pt, n, h)
        old_20_t2 = calculate_old_20_target(pt, n, h)

        if t2 is not None and abs(t2 - canonical_t2) <= tolerance:
            already_correct.append(idx)
        elif t2 is not None and abs(t2 - old_20_t2) <= tolerance:
            confirmed_20.append(idx)
        else:
            outliers.append(idx)

    # 4. Determine records to migrate
    indices_to_migrate = list(confirmed_20)
    if include_outliers:
        indices_to_migrate.extend(outliers)

    w_migrated = 0
    m_migrated = 0
    migrated_alerts = []

    # Deep copy for verification
    original_alerts = copy.deepcopy(alerts)

    for idx in indices_to_migrate:
        alert = alerts[idx]
        pt = alert.get("pattern_type")
        n = alert.get("neckline_price")
        h = alert.get("pattern_height")
        _, canonical_t2 = calculate_canonical_targets(pt, n, h)

        old_val = alert.get("target_2")
        alert["target_2"] = canonical_t2
        migrated_alerts.append((alert.get("alert_id"), pt, old_val, canonical_t2))

        if pt == "W":
            w_migrated += 1
        elif pt == "M":
            m_migrated += 1

    total_migrated = len(indices_to_migrate)

    # 5. Verify that ONLY target_2 changed and no other fields were touched
    for idx, alert in enumerate(alerts):
        orig = original_alerts[idx]
        for k in orig:
            if k == "target_2":
                continue
            assert alert.get(k) == orig.get(k), (
                f"FATAL: Field '{k}' changed in alert {alert.get('alert_id')}! "
                f"Original: {orig.get(k)}, New: {alert.get(k)}"
            )
        assert len(alert) == len(orig), f"FATAL: Key count changed in alert {alert.get('alert_id')}!"

    # 6. Verify duplicates
    alert_ids = [a.get("alert_id") for a in alerts]
    unique_ids = set(alert_ids)
    duplicates_count = len(alert_ids) - len(unique_ids)
    assert duplicates_count == 0, f"FATAL: Found {duplicates_count} duplicate alert IDs!"

    total_after = len(alerts)
    assert total_before == total_after, f"FATAL: Count mismatch! Before: {total_before}, After: {total_after}"

    # 7. Post-migration verification
    remaining_20_count = 0
    remaining_mismatch_count = 0
    for alert in alerts:
        pt = alert.get("pattern_type")
        n = alert.get("neckline_price")
        h = alert.get("pattern_height")
        t2 = alert.get("target_2")
        if pt not in ["W", "M"] or n is None or h is None:
            continue
        _, can_t2 = calculate_canonical_targets(pt, n, h)
        old_20 = calculate_old_20_target(pt, n, h)

        if t2 is not None and abs(t2 - old_20) <= tolerance:
            remaining_20_count += 1
        if t2 is not None and abs(t2 - can_t2) > tolerance:
            remaining_mismatch_count += 1

    # 8. Save updated store if not dry run
    if not dry_run and total_migrated > 0:
        if is_dict:
            data["alerts"] = alerts
        else:
            data = alerts

        temp_store_path = store_path.with_suffix(".tmp")
        with open(temp_store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_store_path.replace(store_path)
        print(f"[SUCCESS] Successfully wrote migrated store to: {store_path}")
    elif dry_run:
        print("[DRY-RUN] No changes were written to disk.")
    else:
        print("[INFO] Store is already 100% up-to-date. No changes written.")

    results = {
        "total_before": total_before,
        "total_after": total_after,
        "total_migrated": total_migrated,
        "w_migrated": w_migrated,
        "m_migrated": m_migrated,
        "already_correct": len(already_correct),
        "remaining_20": remaining_20_count,
        "remaining_mismatches": remaining_mismatch_count,
        "duplicates_created": duplicates_count,
        "outliers_count": len(outliers),
        "outlier_ids": [alerts[i].get("alert_id") for i in outliers]
    }
    return results

def main():
    parser = argparse.ArgumentParser(description="Migrate historical W/M Target 2 values to 1.618x")
    parser.add_argument("--store-path", type=str, default=str(DEFAULT_STORE_PATH), help="Path to alerts store json")
    parser.add_argument("--backup-path", type=str, default=str(BACKUP_PATH), help="Path to backup json")
    parser.add_argument("--include-outliers", action="store_true", help="Also migrate non-standard legacy outlier records")
    parser.add_argument("--dry-run", action="store_true", help="Audit without modifying store")
    args = parser.parse_args()

    results = run_migration(
        store_path=Path(args.store_path),
        backup_path=Path(args.backup_path),
        include_outliers=args.include_outliers,
        dry_run=args.dry_run
    )

    print("\n" + "=" * 50)
    print("MIGRATION AUDIT & EXECUTION REPORT")
    print("=" * 50)
    print(f"1. Total alerts before migration: {results['total_before']}")
    print(f"2. Total alerts after migration:  {results['total_after']}")
    print(f"3. W alerts migrated:            {results['w_migrated']}")
    print(f"4. M alerts migrated:            {results['m_migrated']}")
    print(f"5. Total alerts migrated:        {results['total_migrated']}")
    print(f"6. Alerts already using 1.618x:  {results['already_correct']}")
    print(f"7. Remaining 2.0x T2 records:    {results['remaining_20']}")
    print(f"8. Remaining T2 mismatches:      {results['remaining_mismatches']}")
    print(f"9. Duplicate alerts created:     {results['duplicates_created']}")
    print(f"10. Legacy outlier records:      {results['outliers_count']}")
    print("=" * 50)

if __name__ == "__main__":
    main()
