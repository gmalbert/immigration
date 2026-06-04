"""
scripts/ingest.py — Load an EOIR bronze release into DuckDB.

Usage:
    python scripts/ingest.py --release 2026-05

Reads pipe-delimited tables from bronze/YYYY-MM/ and loads them into
a DuckDB database at silver/YYYY-MM.duckdb for diff processing.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

import duckdb

from utils.eoir_api import EOIR_TABLE_PKS, EOIR_TABLE_ALTERNATIVES, load_eoir_table_to_duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
BRONZE_DIR = ROOT / "bronze"
SILVER_DIR = ROOT / "silver"

CORE_TABLES = [
    "A_TblCase",
    "B_TblProceeding",
    "E_TblApplication",
    "tblLookupHloc",
    "tblLookupJudge",
    "tblLookupCourtDecision",
    "tblLookUp_Appln",
    "tblLookupNationality",
]


def _find_table_file(release_dir: Path, table_name: str) -> Path | None:
    """
    Find the actual file path for a table, considering alternative names.
    Returns None if not found.
    """
    names = [table_name, *EOIR_TABLE_ALTERNATIVES.get(table_name, [])]
    for name in names:
        for ext in (".txt", ".csv"):
            direct = release_dir / f"{name}{ext}"
            if direct.exists():
                return direct
            matches = list(release_dir.rglob(f"{name}{ext}"))
            if matches:
                return matches[0]
    
    return None


def ingest_release(
    release_tag: str,
    tables: list[str] | None = None,
    db_path: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """
    Load all major EOIR tables from a bronze release into a DuckDB database.
    Returns the DuckDB connection (caller is responsible for closing).
    """
    release_dir = BRONZE_DIR / release_tag
    if not release_dir.exists():
        raise FileNotFoundError(f"Bronze release not found: {release_dir}")

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    db_path = db_path or SILVER_DIR / f"{release_tag}.duckdb"

    log.info("Ingesting %s → %s", release_dir, db_path)
    con = duckdb.connect(str(db_path))

    selected_tables = tables or CORE_TABLES

    audit_rows = []
    for table_name in selected_tables:
        row_count = load_eoir_table_to_duckdb(release_dir, table_name, con)
        if row_count == 0:
            log.warning("  Skipped %s (empty or missing)", table_name)
        else:
            log.info("  Loaded %s: %d rows", table_name, row_count)
        audit_rows.append((table_name, row_count))

    # Persist ingest audit
    values = ", ".join(f"('{t}', {c})" for t, c in audit_rows) or "('_none', 0)"
    con.execute(f"""
        CREATE OR REPLACE TABLE _ingest_audit AS
        SELECT * FROM (VALUES {values}) AS t(table_name, row_count)
    """)
    con.execute("CHECKPOINT")
    log.info("✅ Ingest complete for release %s", release_tag)
    return con


def list_bronze_releases() -> list[str]:
    """Return sorted list of available bronze release tags."""
    if not BRONZE_DIR.exists():
        return []
    return sorted(
        d.name for d in BRONZE_DIR.iterdir()
        if d.is_dir() and _find_table_file(d, "A_TblCase")
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest EOIR bronze release into DuckDB")
    parser.add_argument(
        "--release",
        default=None,
        help="Release tag (YYYY-MM). Defaults to latest available.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=None,
        help="Specific EOIR tables to load. Defaults to the core app tables.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Load every table listed in EOIR_TABLE_PKS instead of the core app tables.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional DuckDB output path. Defaults to silver/<release>.duckdb.",
    )
    args = parser.parse_args()

    if args.release:
        release_tag = args.release
    else:
        releases = list_bronze_releases()
        if not releases:
            print("No bronze releases found. Run scripts/download.py first.")
            sys.exit(1)
        release_tag = releases[-1]
        log.info("Using latest release: %s", release_tag)

    tables = list(EOIR_TABLE_PKS) if args.all else args.tables
    db_path = Path(args.db_path) if args.db_path else None
    con = ingest_release(release_tag, tables=tables, db_path=db_path)
    con.close()
