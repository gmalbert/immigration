"""
scripts/aggregate.py - Build Gold-layer Parquet files for the Streamlit UI.

Reads the canonical Silver DuckDB database and writes compact, UI-compatible
Parquet files to /data. These files are safe to commit for instant deploys.

Usage:
    python scripts/aggregate.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CANONICAL_DB = ROOT / "silver" / "canonical.duckdb"
DATA_DIR = ROOT / "data"

FY_EXPR = """
CASE
    WHEN TRY_CAST(p.DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
    WHEN MONTH(TRY_CAST(p.DECISION_DATE AS TIMESTAMP)) >= 10
        THEN YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP)) + 1
    ELSE YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP))
END
"""

ASYLUM_CODES = "('ASY', 'ASYL')"
GRANT_CODES = "('G', 'GR', 'A')"
DENY_CODES = "('D', 'DEN', 'R')"
ASYLUM_DECISION_CODES = "('G', 'GR', 'A', 'D', 'DEN', 'R')"


def get_con() -> duckdb.DuckDBPyConnection:
    if not CANONICAL_DB.exists():
        raise FileNotFoundError(
            f"Canonical DB not found: {CANONICAL_DB}\nRun scripts/canonical.py first."
        )
    return duckdb.connect(str(CANONICAL_DB), read_only=True)


def save(df: pd.DataFrame, name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{name}.parquet"
    df.to_parquet(out, index=False)
    log.info("  Wrote %s: %d rows", out.name, len(df))


def write_json(data: dict, name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("  Wrote %s", name)


def build_judge_metrics(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        SELECT
            p.IJ_CODE AS judge_id,
            p.IJ_CODE AS judge_code,
            COALESCE(NULLIF(p.JUDGE_NAME, ''), p.IJ_CODE) AS judge_name,
            p.COURT AS court_code,
            COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
            p.COURT_STATE AS state,
            p.CIRCUIT AS circuit,
            COUNT(DISTINCT p.IDNPROCEEDING) AS total_proceedings,
            COUNT(DISTINCT p.IDNCASE) AS total_cases,
            ROUND(
                COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                                   AND a.DECISION IN {ASYLUM_DECISION_CODES} THEN a.IDNAPPLICATION END), 0),
                4
            ) AS asylum_grant_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%REMOV%'
                           OR UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%DEPORT%'
                         THEN p.IDNPROCEEDING END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS removal_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN p.IDNPROCEEDING END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS in_absentia_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                         THEN p.IDNCASE END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNCASE), 0),
                4
            ) AS representation_rate,
            GREATEST(
                1,
                COALESCE(
                    MAX(YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP)))
                    - MIN(YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP))) + 1,
                    1
                )
            ) AS years_on_bench
        FROM canonical_proceedings p
        LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
        LEFT JOIN canonical_applications a ON a.IDNPROCEEDING = p.IDNPROCEEDING
        WHERE p._current = TRUE
          AND p.IJ_CODE IS NOT NULL
          AND p.IJ_CODE != ''
        GROUP BY p.IJ_CODE, p.JUDGE_NAME, p.COURT, p.COURT_CITY, p.COURT_STATE, p.CIRCUIT
        HAVING total_cases >= 10
        ORDER BY total_cases DESC
    """).df()
    save(df, "judge_metrics")


def build_court_metrics(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        SELECT
            p.COURT AS court_code,
            COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
            p.COURT_STATE AS state,
            p.CIRCUIT AS circuit,
            COUNT(DISTINCT p.IDNPROCEEDING) AS total_proceedings,
            COUNT(DISTINCT p.IDNCASE) AS total_cases,
            COUNT(DISTINCT CASE WHEN p.DECISION_DATE IS NULL OR p.DECISION_DATE = '' THEN p.IDNCASE END) AS pending_cases,
            ROUND(
                COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                                   AND a.DECISION IN {ASYLUM_DECISION_CODES} THEN a.IDNAPPLICATION END), 0),
                4
            ) AS asylum_grant_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                         THEN p.IDNCASE END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNCASE), 0),
                4
            ) AS representation_rate
        FROM canonical_proceedings p
        LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
        LEFT JOIN canonical_applications a ON a.IDNPROCEEDING = p.IDNPROCEEDING
        WHERE p._current = TRUE
          AND p.COURT IS NOT NULL
          AND p.COURT != ''
        GROUP BY p.COURT, p.COURT_CITY, p.COURT_STATE, p.CIRCUIT
        ORDER BY total_cases DESC
    """).df()
    save(df, "court_metrics")
    write_json(dict(zip(df["court_code"], df["court_city"])), "court_lookup.json")


def build_nationality_metrics(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        WITH base AS (
            SELECT
                c.IDNCASE,
                c.ATTY_NBR,
                p.IDNPROCEEDING,
                a.IDNAPPLICATION,
                a.APPLICATION_TYPE,
                a.DECISION,
                COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, '')) AS nat_code,
                COALESCE(NULLIF(n.NAT_COUNTRY_NAME, ''), NULLIF(n.NAT_NAME, ''),
                         COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, ''))) AS country_name
            FROM canonical_cases c
            LEFT JOIN canonical_proceedings p ON p.IDNCASE = c.IDNCASE
            LEFT JOIN canonical_applications a ON a.IDNPROCEEDING = p.IDNPROCEEDING
            LEFT JOIN canonical_nationalities n ON n.NAT_CODE = COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, ''))
            WHERE c._current = TRUE
        )
        SELECT
            nat_code,
            COUNT(DISTINCT IDNCASE) AS case_count,
            ROUND(
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                                   AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END), 0),
                4
            ) AS asylum_grant_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN ATTY_NBR IS NOT NULL AND ATTY_NBR NOT IN ('', '0')
                         THEN IDNCASE END)::DOUBLE
                / NULLIF(COUNT(DISTINCT IDNCASE), 0),
                4
            ) AS representation_rate,
            country_name
        FROM base
        GROUP BY nat_code, country_name
        HAVING nat_code IS NOT NULL AND nat_code != '' AND case_count >= 20
        ORDER BY case_count DESC
    """).df()
    save(df, "nationality_metrics")
    write_json(dict(zip(df["nat_code"], df["country_name"])), "nationality_lookup.json")


def build_case_outcomes(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        SELECT
            {FY_EXPR} AS fiscal_year,
            COALESCE(NULLIF(p.OUTCOME_DESCRIPTION, ''), NULLIF(p.OUTCOME, ''), 'Unknown') AS outcome_type,
            COUNT(DISTINCT p.IDNPROCEEDING) AS case_count
        FROM canonical_proceedings p
        WHERE p._current = TRUE
          AND {FY_EXPR} BETWEEN 1990 AND 2027
        GROUP BY fiscal_year, outcome_type
        ORDER BY fiscal_year, case_count DESC
    """).df()
    save(df, "case_outcomes")


def build_representation_gap(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        SELECT
            {FY_EXPR} AS fiscal_year,
            ROUND(
                COUNT(DISTINCT CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                          AND a.APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                                    AND a.APPLICATION_TYPE IN {ASYLUM_CODES}
                                    AND a.DECISION IN {ASYLUM_DECISION_CODES}
                                  THEN a.IDNAPPLICATION END), 0),
                4
            ) AS represented_grant_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN (c.ATTY_NBR IS NULL OR c.ATTY_NBR IN ('', '0'))
                          AND a.APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN (c.ATTY_NBR IS NULL OR c.ATTY_NBR IN ('', '0'))
                                    AND a.APPLICATION_TYPE IN {ASYLUM_CODES}
                                    AND a.DECISION IN {ASYLUM_DECISION_CODES}
                                  THEN a.IDNAPPLICATION END), 0),
                4
            ) AS prose_grant_rate,
            ROUND(
                COUNT(DISTINCT CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                         THEN p.IDNCASE END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNCASE), 0),
                4
            ) AS representation_rate
        FROM canonical_proceedings p
        JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
        LEFT JOIN canonical_applications a ON a.IDNPROCEEDING = p.IDNPROCEEDING
        WHERE p._current = TRUE
          AND {FY_EXPR} BETWEEN 2000 AND 2027
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """).df()
    save(df, "representation_gap")


def build_policy_trends(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        SELECT
            {FY_EXPR} AS fiscal_year,
            COUNT(DISTINCT p.IDNPROCEEDING) AS total_completions,
            ROUND(
                SUM(CASE WHEN UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%ADMIN%'
                           OR UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%CLOS%'
                         THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS admin_closure_rate,
            ROUND(
                SUM(CASE WHEN UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%TERM%'
                           OR UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%DISMISS%'
                         THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS termination_rate,
            ROUND(
                SUM(CASE WHEN p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS in_absentia_rate
        FROM canonical_proceedings p
        WHERE p._current = TRUE
          AND {FY_EXPR} BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """).df()
    save(df, "policy_trends")


def build_in_absentia(con: duckdb.DuckDBPyConnection) -> None:
    timeline = con.execute(f"""
        WITH base AS (
            SELECT
                {FY_EXPR} AS fiscal_year,
                SUM(CASE WHEN p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN 1 ELSE 0 END) AS in_absentia_orders,
                COUNT(DISTINCT p.IDNPROCEEDING) AS total_merits_hearings,
                SUM(CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                          AND p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN 1 ELSE 0 END) AS represented_ia_orders,
                SUM(CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                         THEN 1 ELSE 0 END) AS represented_total,
                SUM(CASE WHEN (c.ATTY_NBR IS NULL OR c.ATTY_NBR IN ('', '0'))
                          AND p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN 1 ELSE 0 END) AS unrepresented_ia_orders,
                SUM(CASE WHEN c.ATTY_NBR IS NULL OR c.ATTY_NBR IN ('', '0')
                         THEN 1 ELSE 0 END) AS unrepresented_total
            FROM canonical_proceedings p
            LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
            WHERE p._current = TRUE
              AND {FY_EXPR} BETWEEN 1990 AND 2027
            GROUP BY fiscal_year
        )
        SELECT
            fiscal_year,
            in_absentia_orders,
            total_merits_hearings,
            ROUND(in_absentia_orders::DOUBLE / NULLIF(total_merits_hearings, 0), 4) AS in_absentia_rate,
            ROUND(represented_ia_orders::DOUBLE / NULLIF(represented_total, 0), 4) AS represented_ia_rate,
            ROUND(unrepresented_ia_orders::DOUBLE / NULLIF(unrepresented_total, 0), 4) AS unrepresented_ia_rate,
            NULL::TEXT AS admin
        FROM base
        ORDER BY fiscal_year
    """).df()
    save(timeline, "in_absentia_timeline")

    by_court = con.execute("""
        SELECT
            p.COURT AS court_code,
            COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
            p.CIRCUIT AS circuit,
            ROUND(
                SUM(CASE WHEN p.ABSENTIA IS NOT NULL AND p.ABSENTIA NOT IN ('', 'N', '0')
                         THEN 1 ELSE 0 END)::DOUBLE
                / NULLIF(COUNT(DISTINCT p.IDNPROCEEDING), 0),
                4
            ) AS in_absentia_rate,
            COUNT(DISTINCT p.IDNPROCEEDING) AS case_count
        FROM canonical_proceedings p
        WHERE p._current = TRUE
          AND p.COURT IS NOT NULL
          AND p.COURT != ''
        GROUP BY p.COURT, p.COURT_CITY, p.CIRCUIT
        HAVING case_count >= 50
        ORDER BY in_absentia_rate DESC
    """).df()
    save(by_court, "in_absentia_by_court")


def build_backlog_timeline(con: duckdb.DuckDBPyConnection) -> None:
    latest = con.execute("""
        SELECT MAX(_last_seen_release) FROM canonical_cases
    """).fetchone()[0]
    pending = con.execute("""
        SELECT COUNT(DISTINCT p.IDNCASE)
        FROM canonical_proceedings p
        WHERE p._current = TRUE
          AND (p.DECISION_DATE IS NULL OR p.DECISION_DATE = '')
    """).fetchone()[0]
    year = int(str(latest).split("-")[0]) if latest else datetime.now().year
    save(pd.DataFrame([{"fiscal_year": year, "pending_cases": pending}]), "backlog_timeline")


def build_empty_unsupported_tables() -> None:
    """Replace seed-only tables with empty, schema-compatible outputs."""
    empty_tables = {
        "bond_analytics": [
            "fiscal_year", "total_hearings", "bond_granted", "grant_rate",
            "median_bond", "detention_rate_post", "admin", "bond_denied",
        ],
        "uac_metrics": [
            "fiscal_year", "apprehensions", "grant_rate", "representation_rate",
            "removal_rate", "admin",
        ],
        "uac_origin": ["era", "nat_code", "count"],
        "detention_timeline": [
            "fiscal_year", "avg_daily_pop", "detention_beds_funded", "book_ins",
            "avg_length_of_stay_days", "civil_pct", "criminal_pct", "ice_facilities",
        ],
        "detention_by_facility": ["facility_type", "pct_of_pop", "avg_alos_days", "avg_daily_cost_usd"],
        "removal_orders": ["fiscal_year", "removal_type", "count", "admin"],
        "removal_by_nationality": ["nat_code", "country", "total_removals", "expedited_pct"],
        "bia_timeline": [
            "fiscal_year", "receipts", "completions", "dismissed", "sustained",
            "remanded", "dhs_appeals", "pending", "admin",
        ],
        "circuit_appeals": [
            "circuit", "circuit_name", "key_states", "petitions_filed",
            "granted_remanded", "reversal_rate", "median_days", "notable_case",
        ],
        "case_age_timeline": [
            "fiscal_year", "median_days", "p25_days", "p75_days",
            "detained_median", "nondetained_median", "represented_median", "prose_median", "admin",
        ],
        "case_age_by_court": [
            "court_city", "state", "circuit", "median_days", "pct_5yr_plus", "total_pending",
        ],
        "backlog_age_dist": ["age_bucket", "count", "color"],
    }
    for table, cols in empty_tables.items():
        save(pd.DataFrame(columns=cols), table)


def write_pipeline_status(con: duckdb.DuckDBPyConnection) -> None:
    total_cases = con.execute("SELECT COUNT(*) FROM canonical_cases WHERE _current = TRUE").fetchone()[0]
    total_procs = con.execute("SELECT COUNT(*) FROM canonical_proceedings WHERE _current = TRUE").fetchone()[0]
    total_apps = con.execute("SELECT COUNT(*) FROM canonical_applications WHERE _current = TRUE").fetchone()[0]
    deletions = con.execute("""
        SELECT
            (SELECT COUNT(*) FROM canonical_cases WHERE _ever_deleted = TRUE)
          + (SELECT COUNT(*) FROM canonical_proceedings WHERE _ever_deleted = TRUE)
          + (SELECT COUNT(*) FROM canonical_applications WHERE _ever_deleted = TRUE)
    """).fetchone()[0]
    latest_release = con.execute("SELECT MAX(_last_seen_release) FROM canonical_cases").fetchone()[0] or ""

    status = {
        "last_release": latest_release,
        "data_source": "EOIR CASE database canonical pipeline",
        "total_cases": total_cases,
        "total_proceedings": total_procs,
        "total_applications": total_apps,
        "quality_warnings": 1 if deletions else 0,
        "deletion_count": deletions,
        "seed_mode": False,
        "last_run": datetime.now().isoformat(),
        "note": "Gold data generated from the local EOIR CASE release via ingest -> canonical -> aggregate.",
    }
    write_json(status, "pipeline_status.json")


def run_all() -> None:
    log.info("Starting Gold layer aggregation...")
    con = get_con()
    build_judge_metrics(con)
    build_court_metrics(con)
    build_nationality_metrics(con)
    build_case_outcomes(con)
    build_representation_gap(con)
    build_policy_trends(con)
    build_in_absentia(con)
    build_backlog_timeline(con)
    build_empty_unsupported_tables()
    write_pipeline_status(con)
    con.close()
    log.info("Gold aggregation complete. Data written to /data/")


if __name__ == "__main__":
    run_all()
