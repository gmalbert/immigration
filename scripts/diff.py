"""
scripts/diff.py — Compare two monthly EOIR releases for disappearing records.

Usage:
    python scripts/diff.py --prev 2026-04 --curr 2026-05

This is the most critical data integrity step. Based on TRAC's methodology
for detecting EOIR's documented disappearing-records problem.

Outputs:
  silver/diff_log/CURR_TABLE_deletions.csv  — any deleted records
  silver/diff_log/CURR_summary.csv          — per-table diff summary
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

import pandas as pd

from utils.eoir_api import EOIR_TABLE_PKS, load_eoir_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
BRONZE_DIR = ROOT / "bronze"
DIFF_LOG_DIR = ROOT / "silver" / "diff_log"

# Deletion rate thresholds that trigger a pipeline halt recommendation
ALERT_THRESHOLDS = {
    "A_TblCase":        0.001,   # >0.1% case deletions
    "E_TblApplication": 0.005,   # >0.5% application deletions (historically volatile)
    "B_TblProceeding":  0.001,
}


def diff_table(
    prev_dir: Path,
    curr_dir: Path,
    table_name: str,
    primary_key: str,
) -> dict:
    """
    Diff a single table between two releases.
    Returns a summary dict. Saves a deletions CSV if records were removed.
    """
    prev_df = load_eoir_table(prev_dir, table_name)
    curr_df = load_eoir_table(curr_dir, table_name)

    if prev_df.empty or curr_df.empty:
        return {"table": table_name, "error": "File missing or empty in one release"}

    pk = primary_key.upper()
    if pk not in prev_df.columns:
        return {"table": table_name, "error": f"PK '{pk}' not found in columns"}

    prev_ids = set(prev_df[pk].dropna())
    curr_ids = set(curr_df[pk].dropna())

    deleted_ids = prev_ids - curr_ids
    added_ids   = curr_ids - prev_ids

    deletion_rate = len(deleted_ids) / max(len(prev_ids), 1)

    summary = {
        "table":              table_name,
        "prev_count":         len(prev_ids),
        "curr_count":         len(curr_ids),
        "added":              len(added_ids),
        "deleted":            len(deleted_ids),
        "deletion_rate_pct":  round(deletion_rate * 100, 4),
    }

    if deleted_ids:
        deleted_df = prev_df[prev_df[pk].isin(deleted_ids)].copy()
        deleted_df["_deleted_from_release"] = curr_dir.name
        deleted_df["_last_present_release"] = prev_dir.name

        DIFF_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DIFF_LOG_DIR / f"{curr_dir.name}_{table_name}_deletions.csv"
        deleted_df.to_csv(log_path, index=False)
        log.warning("  ⚠ %s: %d DELETIONS (%.4f%%) → %s",
                    table_name, len(deleted_ids), deletion_rate * 100, log_path)

    threshold = ALERT_THRESHOLDS.get(table_name, 0.01)
    if deletion_rate > threshold:
        log.error(
            "  🚨 ALERT: %s — %.4f%% deletion rate exceeds threshold %.4f%%. "
            "Do NOT publish until investigated.",
            table_name, deletion_rate * 100, threshold * 100,
        )
        summary["alert"] = True

    return summary


def diff_releases(prev_tag: str, curr_tag: str) -> pd.DataFrame:
    """
    Diff all major EOIR tables between two release months.
    Returns a summary DataFrame and saves to diff_log/.
    """
    prev_dir = BRONZE_DIR / prev_tag
    curr_dir = BRONZE_DIR / curr_tag

    for d, tag in [(prev_dir, prev_tag), (curr_dir, curr_tag)]:
        if not d.exists():
            raise FileNotFoundError(f"Bronze release not found: {d} (tag={tag})")

    log.info("Diffing %s → %s", prev_tag, curr_tag)
    summaries = []
    for table_name, pk in EOIR_TABLE_PKS.items():
        result = diff_table(prev_dir, curr_dir, table_name, pk)
        summaries.append(result)

    summary_df = pd.DataFrame(summaries)
    DIFF_LOG_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DIFF_LOG_DIR / f"{curr_tag}_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    log.info("Diff summary → %s", summary_path)

    alerts = summary_df[summary_df.get("deletion_rate_pct", pd.Series(dtype=float)) > 0.1]
    if not alerts.empty:
        log.warning(
            "\n🚨 %d tables have elevated deletion rates. "
            "Review %s before running canonical.py.",
            len(alerts), summary_path,
        )

    return summary_df


if __name__ == "__main__":
    from scripts.ingest import list_bronze_releases

    parser = argparse.ArgumentParser(description="Diff two EOIR monthly releases")
    releases = list_bronze_releases()
    parser.add_argument("--prev", default=releases[-2] if len(releases) >= 2 else None)
    parser.add_argument("--curr", default=releases[-1] if releases else None)
    args = parser.parse_args()

    if not args.prev or not args.curr:
        print("Need at least two bronze releases. Run scripts/download.py first.")
        sys.exit(1)

    diff_releases(args.prev, args.curr)
