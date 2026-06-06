"""
Relief Docket – data loading layer.

Loads gold-layer Parquet files from /data/ for the UI.
Falls back gracefully when no data has been downloaded yet.

Gold tables (written by scripts/aggregate.py):
  data/judge_metrics.parquet
  data/court_metrics.parquet
  data/nationality_metrics.parquet
  data/case_outcomes.parquet
  data/backlog_timeline.parquet
  data/representation_gap.parquet
  data/policy_trends.parquet
  data/admin_closure_rates.parquet
  data/pipeline_status.json
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_DATA = _ROOT / "data"
_SILVER_DB = _ROOT / "silver" / "canonical.duckdb"

ROADMAP_OUTPUTS = [
    {"table": "judge_metrics_by_year", "label": "Judge metrics by fiscal year"},
    {"table": "court_metrics_by_year", "label": "Court metrics by fiscal year"},
    {"table": "nationality_metrics_by_year", "label": "Nationality outcomes by fiscal year"},
    {"table": "representation_by_court", "label": "Representation impact by court"},
    {"table": "representation_by_nationality", "label": "Representation impact by nationality"},
    {"table": "case_age_by_case_type", "label": "Case age by case type"},
    {"table": "case_age_by_judge", "label": "Case age by judge"},
    {"table": "hearing_schedule_metrics", "label": "Hearing schedule metrics"},
    {"table": "continuance_metrics", "label": "Continuance metrics"},
    {"table": "bond_by_year", "label": "Bond analytics by fiscal year"},
    {"table": "bond_by_court", "label": "Bond analytics by court"},
    {"table": "bond_by_judge", "label": "Bond analytics by judge"},
    {"table": "custody_transitions", "label": "Custody transitions"},
    {"table": "appeal_outcomes_by_type", "label": "Appeal outcomes by type and party"},
    {"table": "representation_details", "label": "Attorney and representation detail"},
    {"table": "charge_analysis", "label": "Charge-level analysis"},
    {"table": "charge_outcomes", "label": "Charge outcomes"},
    {"table": "motion_activity", "label": "Motion activity"},
    {"table": "release_snapshot_tracking", "label": "Release snapshot tracking"},
    {"table": "data_quality_summary", "label": "Data quality audit summary"},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def data_dir() -> Path:
    _DATA.mkdir(parents=True, exist_ok=True)
    return _DATA


def has_gold(table: str) -> bool:
    """Return True if a gold parquet file exists for this table."""
    return (_DATA / f"{table}.parquet").exists()


def has_any_data() -> bool:
    """Return True if any gold layer data has been built."""
    return any(_DATA.glob("*.parquet"))


def get_pipeline_status() -> dict:
    """Return the latest pipeline status dict (or empty defaults)."""
    status_path = _DATA / "pipeline_status.json"
    defaults = {
        "last_release": None,
        "total_cases": 0,
        "total_proceedings": 0,
        "quality_warnings": 0,
        "last_run": None,
    }
    if status_path.exists():
        try:
            with open(status_path, encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
        except Exception:
            pass
    return defaults


@st.cache_data(ttl=3600, show_spinner=False)
def load_gold_table(table: str) -> Optional[pd.DataFrame]:
    """Load an arbitrary gold-layer Parquet table by base file name."""
    path = _DATA / f"{table}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading %s: %s", table, e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def list_roadmap_outputs() -> pd.DataFrame:
    """Return file-level metadata for implemented roadmap output tables."""
    rows = []
    for item in ROADMAP_OUTPUTS:
        table = item["table"]
        path = _DATA / f"{table}.parquet"
        row_count = None
        column_count = None
        if path.exists():
            try:
                df = pd.read_parquet(path)
                row_count = len(df)
                column_count = len(df.columns)
            except Exception as e:
                log.warning("Failed inspecting %s: %s", table, e)
        rows.append({
            "table": table,
            "label": item["label"],
            "exists": path.exists(),
            "rows": row_count,
            "columns": column_count,
            "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else None,
        })
    return pd.DataFrame(rows)


# ── Gold-layer loaders (cached) ───────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_judge_metrics() -> Optional[pd.DataFrame]:
    """Judge-level metrics: grant rate, removal rate, case volume, etc."""
    path = _DATA / "judge_metrics.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading judge_metrics: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_court_metrics() -> Optional[pd.DataFrame]:
    """Court-level metrics: backlog, grant rates, representation rates."""
    path = _DATA / "court_metrics.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading court_metrics: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_nationality_metrics() -> Optional[pd.DataFrame]:
    """Nationality-level metrics: grant rates, volume trends."""
    path = _DATA / "nationality_metrics.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading nationality_metrics: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_case_outcomes() -> Optional[pd.DataFrame]:
    """Aggregate case outcomes by year and outcome type."""
    path = _DATA / "case_outcomes.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading case_outcomes: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_case_outcomes_annual() -> Optional[pd.DataFrame]:
    """Precomputed annual case outcome summary, wide by outcome type."""
    path = _DATA / "case_outcomes_annual.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading case_outcomes_annual: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_backlog_timeline() -> Optional[pd.DataFrame]:
    """Pending caseload over time."""
    path = _DATA / "backlog_timeline.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading backlog_timeline: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_representation_gap() -> Optional[pd.DataFrame]:
    """Representation gap data: represented vs pro se outcome rates."""
    path = _DATA / "representation_gap.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading representation_gap: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_policy_trends() -> Optional[pd.DataFrame]:
    """Policy-sensitive metrics over time (admin closure, terminations, etc.)."""
    path = _DATA / "policy_trends.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading policy_trends: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_bond_analytics() -> Optional[pd.DataFrame]:
    """Bond grant rates and amounts by court, judge, nationality."""
    path = _DATA / "bond_analytics.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading bond_analytics: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_uac_metrics() -> Optional[pd.DataFrame]:
    """Unaccompanied children — annual arrival and outcome metrics."""
    path = _DATA / "uac_metrics.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading uac_metrics: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_uac_origin() -> Optional[pd.DataFrame]:
    """Unaccompanied children — country of origin breakdown."""
    path = _DATA / "uac_origin.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading uac_origin: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_in_absentia_timeline() -> Optional[pd.DataFrame]:
    """In absentia removal orders — annual timeline with represented vs unrepresented rates."""
    path = _DATA / "in_absentia_timeline.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading in_absentia_timeline: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_in_absentia_by_court() -> Optional[pd.DataFrame]:
    """In absentia rates broken down by immigration court."""
    path = _DATA / "in_absentia_by_court.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading in_absentia_by_court: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_detention_timeline() -> Optional[pd.DataFrame]:
    """ICE detention — annual average daily population, bed counts, book-ins."""
    path = _DATA / "detention_timeline.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading detention_timeline: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_detention_by_facility() -> Optional[pd.DataFrame]:
    """ICE detention breakdown by facility type."""
    path = _DATA / "detention_by_facility.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading detention_by_facility: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_removal_orders() -> Optional[pd.DataFrame]:
    """Annual removal orders broken down by removal type."""
    path = _DATA / "removal_orders.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading removal_orders: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_removal_by_nationality() -> Optional[pd.DataFrame]:
    """Recent removal counts by top nationality."""
    path = _DATA / "removal_by_nationality.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading removal_by_nationality: %s", e)
        return None


def load_bia_timeline() -> Optional[pd.DataFrame]:
    """BIA appeal receipts, completions, outcomes by fiscal year.

    This intentionally avoids Streamlit's one-hour cache because the appeal
    aggregate has been iterated frequently during data QA. Reading the small
    Parquet directly prevents a running app from showing stale zeroed outcomes.
    """
    path = _DATA / "bia_timeline.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading bia_timeline: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_circuit_appeals() -> Optional[pd.DataFrame]:
    """Federal petition-for-review trend from EOIR appeal records."""
    path = _DATA / "circuit_appeals.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading circuit_appeals: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_case_age_timeline() -> Optional[pd.DataFrame]:
    """National case processing time trend by fiscal year."""
    path = _DATA / "case_age_timeline.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading case_age_timeline: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_case_age_by_court() -> Optional[pd.DataFrame]:
    """Median case processing time by immigration court."""
    path = _DATA / "case_age_by_court.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading case_age_by_court: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_backlog_age_dist() -> Optional[pd.DataFrame]:
    """Distribution of pending cases by how old they are."""
    path = _DATA / "backlog_age_dist.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading backlog_age_dist: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_in_absentia() -> Optional[pd.DataFrame]:
    """In absentia order rates by court, admin, nationality."""
    path = _DATA / "in_absentia.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        log.warning("Failed loading in_absentia: %s", e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_nationality_lookup() -> dict:
    """Return {nat_code: country_name} mapping."""
    path = _DATA / "nationality_lookup.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def load_court_lookup() -> dict:
    """Return {court_code: city_name} mapping."""
    path = _DATA / "court_lookup.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def silver_available() -> bool:
    """Return True if the silver DuckDB canonical database exists."""
    return _SILVER_DB.exists()


def query_silver(sql: str) -> Optional[pd.DataFrame]:
    """
    Run a SELECT query against the silver canonical DuckDB.
    Returns None if the database doesn't exist.
    """
    if not silver_available():
        return None
    try:
        import duckdb
        con = duckdb.connect(str(_SILVER_DB), read_only=True)
        result = con.execute(sql).df()
        con.close()
        return result
    except Exception as e:
        log.warning("Silver query failed: %s", e)
        return None
