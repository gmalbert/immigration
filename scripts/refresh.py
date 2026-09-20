"""
scripts/refresh.py - End-to-end EOIR pipeline orchestrator.

Runs the four pipeline stages synchronously in the foreground:

    download  -> ingest -> canonical -> aggregate

Each stage is invoked as a subprocess so its existing CLI, logging, and
exit code are preserved. A stage marked 'done' for the target release in
``data/.pipeline_stages.json`` is skipped on subsequent runs; pass
``--force`` to re-run a stage regardless.

This script is the single entry point for any automated or manual
monthly refresh. Backgrounding any stage here will be treated as a bug.

Usage:
    python scripts/refresh.py
    python scripts/refresh.py --release 2026-08
    python scripts/refresh.py --stage canonical
    python scripts/refresh.py --force --stage aggregate
    python scripts/refresh.py --status
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
BRONZE_DIR = ROOT / "bronze"
SILVER_DIR = ROOT / "silver"
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / ".pipeline_stages.json"

STAGES = ("download", "ingest", "canonical", "aggregate")
# Both canonical and aggregate target the same canonical DuckDB. The
# historically active file is silver/canonical.roadmap3.duckdb
# (see docs/data_refresh_handoff_2026-09-15.md).
CANONICAL_DB = SILVER_DIR / "canonical.roadmap3.duckdb"
INGEST_DB_TEMPLATE = "{tag}.core2.duckdb"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh")


def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("State file %s is corrupt; treating as empty", STATE_FILE)
        return {}


def _write_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _detect_release(state: dict) -> str:
    """Pick the release to refresh: most recent bronze folder, else most recent
    state entry, else current month."""
    bronze_releases = sorted(p.name for p in BRONZE_DIR.iterdir() if p.is_dir()) if BRONZE_DIR.exists() else []
    if bronze_releases:
        return bronze_releases[-1]
    if state:
        return sorted(state.keys())[-1]
    return datetime.now().strftime("%Y-%m")


def _ingest_db_path(release_tag: str) -> Path:
    return SILVER_DIR / INGEST_DB_TEMPLATE.format(tag=release_tag)


def _is_stage_done(state: dict, release_tag: str, stage: str) -> bool:
    return state.get(release_tag, {}).get(stage, {}).get("status") == "done"


def _mark_stage(state: dict, release_tag: str, stage: str, **fields) -> None:
    state.setdefault(release_tag, {})
    entry = state[release_tag].setdefault(stage, {})
    entry.update({
        "status": fields.pop("status", "done"),
        "at": datetime.now().isoformat(timespec="seconds"),
        **fields,
    })
    _write_state(state)


def _run_stage(stage: str, release_tag: str) -> None:
    """Invoke one stage as a synchronous subprocess. check=True raises on failure."""
    python = sys.executable
    if stage == "download":
        cmd = [python, str(SCRIPTS_DIR / "download.py")]
    elif stage == "ingest":
        cmd = [python, str(SCRIPTS_DIR / "ingest.py"),
               "--release", release_tag,
               "--db-path", str(_ingest_db_path(release_tag))]
    elif stage == "canonical":
        cmd = [python, str(SCRIPTS_DIR / "canonical.py"),
               "--release", release_tag,
               "--ingest-db", str(_ingest_db_path(release_tag)),
               "--canonical-db", str(CANONICAL_DB)]
    elif stage == "aggregate":
        cmd = [python, str(SCRIPTS_DIR / "aggregate.py"),
               "--canonical-db", str(CANONICAL_DB)]
    else:
        raise ValueError(f"unknown stage: {stage}")

    log.info(">>> STAGE: %s", stage)
    log.info("    cmd: %s", " ".join(cmd))
    started = datetime.now()
    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as exc:
        log.error("Stage %s failed with exit code %s", stage, exc.returncode)
        state = _read_state()
        _mark_stage(state, release_tag, stage, status="error",
                    started_at=started.isoformat(timespec="seconds"),
                    returncode=exc.returncode)
        raise
    finished = datetime.now()
    log.info("<<< STAGE %s complete in %ss", stage, (finished - started).seconds)
    state = _read_state()
    extra = {}
    if stage == "ingest":
        extra["ingest_db"] = str(_ingest_db_path(release_tag))
    elif stage == "canonical":
        extra["canonical_db"] = str(CANONICAL_DB)
    elif stage == "aggregate":
        extra["pipeline_status"] = str(DATA_DIR / "pipeline_status.json")
    elif stage == "download":
        extra["release_dir"] = str(BRONZE_DIR / release_tag)
    _mark_stage(state, release_tag, stage,
                started_at=started.isoformat(timespec="seconds"),
                finished_at=finished.isoformat(timespec="seconds"),
                **extra)


def _print_status(state: dict, release_tag: str) -> None:
    print(f"State file: {STATE_FILE}")
    print(f"Release:    {release_tag}")
    print()
    rel = state.get(release_tag, {})
    for stage in STAGES:
        entry = rel.get(stage, {"status": "pending"})
        status = entry.get("status", "pending")
        at = entry.get("at") or entry.get("finished_at") or "-"
        marker = "OK " if status == "done" else ("ERR" if status == "error" else "-- ")
        print(f"  [{marker}] {stage:<10} {status:<8} {at}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the EOIR data refresh pipeline end-to-end.")
    parser.add_argument("--release", default=None,
                        help="Release tag YYYY-MM. Defaults to the latest bronze folder, latest state, or current month.")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all",
                        help="Which stage to run. 'all' runs every stage from the first not-done one.")
    parser.add_argument("--force", action="store_true",
                        help="Re-run a stage even if it is marked done.")
    skip = parser.add_mutually_exclusive_group()
    skip.add_argument("--skip-download", dest="skip_download", action="store_true")
    skip.add_argument("--skip-ingest", dest="skip_ingest", action="store_true")
    skip.add_argument("--skip-canonical", dest="skip_canonical", action="store_true")
    skip.add_argument("--skip-aggregate", dest="skip_aggregate", action="store_true")
    parser.add_argument("--status", action="store_true",
                        help="Print current per-release stage status and exit.")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    state = _read_state()
    release_tag = args.release or _detect_release(state)

    if args.status:
        _print_status(state, release_tag)
        return 0

    skip_set = set()
    if args.skip_download:
        skip_set.add("download")
    if args.skip_ingest:
        skip_set.add("ingest")
    if args.skip_canonical:
        skip_set.add("canonical")
    if args.skip_aggregate:
        skip_set.add("aggregate")

    requested = STAGES if args.stage == "all" else (args.stage,)
    stages_to_run = [s for s in requested if s not in skip_set]
    if not stages_to_run:
        parser.error("No stages to run after applying --skip flags.")

    log.info("Refresh plan: release=%s stages=%s force=%s", release_tag, stages_to_run, args.force)
    _print_status(state, release_tag)
    print()

    for stage in stages_to_run:
        if not args.force and _is_stage_done(state, release_tag, stage):
            log.info("Skipping %s: marked done at %s (use --force to rerun)",
                     stage, state[release_tag][stage].get("at"))
            continue
        _run_stage(stage, release_tag)
        state = _read_state()

    log.info("Refresh complete for release %s", release_tag)
    _print_status(state, release_tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
