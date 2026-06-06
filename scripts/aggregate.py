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


def get_con(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    canonical_db = db_path or CANONICAL_DB
    if not canonical_db.exists():
        raise FileNotFoundError(
            f"Canonical DB not found: {canonical_db}\nRun scripts/canonical.py first."
        )
    temp_dir = ROOT / "tmp" / "duckdb_aggregate"
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(canonical_db), read_only=True)
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET threads=2")
    con.execute(f"SET temp_directory='{temp_dir.as_posix()}'")
    return con


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
        WITH app_by_proceeding AS (
            SELECT
                IDNPROCEEDING,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END) AS asylum_grants,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END) AS asylum_decisions
            FROM canonical_applications
            GROUP BY IDNPROCEEDING
        )
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
                SUM(COALESCE(a.asylum_grants, 0))::DOUBLE
                / NULLIF(SUM(COALESCE(a.asylum_decisions, 0)), 0),
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
        LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = p.IDNPROCEEDING
        WHERE p._current = TRUE
          AND p.IJ_CODE IS NOT NULL
          AND p.IJ_CODE != ''
        GROUP BY p.IJ_CODE, p.JUDGE_NAME, p.COURT, p.COURT_CITY, p.COURT_STATE, p.CIRCUIT
        HAVING total_cases >= 10
        ORDER BY total_cases DESC
    """).df()
    df["grant_pct"] = (df["asylum_grant_rate"] * 100).round(2)
    df["removal_pct"] = (df["removal_rate"] * 100).round(2)
    df["abs_pct"] = (df["in_absentia_rate"] * 100).round(2)
    df["rep_pct"] = (df["representation_rate"] * 100).round(2)
    df["label"] = df["judge_name"] + " - " + df["court_city"]
    court_stats = (
        df.groupby("court_city")["grant_pct"]
        .agg(court_mean="mean", court_std="std", court_median="median",
             court_min="min", court_max="max", court_n="count")
        .reset_index()
    )
    df = df.merge(court_stats, on="court_city", how="left")
    df["z_score"] = ((df["grant_pct"] - df["court_mean"]) /
                     df["court_std"].mask(df["court_std"] == 0)).fillna(0).round(2)
    df["is_outlier"] = df["z_score"].abs() >= 1.5
    save(df, "judge_metrics")


def build_court_metrics(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        WITH app_by_proceeding AS (
            SELECT
                IDNPROCEEDING,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END) AS asylum_grants,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END) AS asylum_decisions
            FROM canonical_applications
            GROUP BY IDNPROCEEDING
        )
        SELECT
            p.COURT AS court_code,
            COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
            p.COURT_STATE AS state,
            p.CIRCUIT AS circuit,
            COUNT(DISTINCT p.IDNPROCEEDING) AS total_proceedings,
            COUNT(DISTINCT p.IDNCASE) AS total_cases,
            COUNT(DISTINCT CASE WHEN p.DECISION_DATE IS NULL OR p.DECISION_DATE = '' THEN p.IDNCASE END) AS pending_cases,
            ROUND(
                SUM(COALESCE(a.asylum_grants, 0))::DOUBLE
                / NULLIF(SUM(COALESCE(a.asylum_decisions, 0)), 0),
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
        LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = p.IDNPROCEEDING
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
        WITH app_by_proceeding AS (
            SELECT
                IDNPROCEEDING,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END) AS asylum_grants,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END) AS asylum_decisions
            FROM canonical_applications
            GROUP BY IDNPROCEEDING
        ),
        base AS (
            SELECT
                c.IDNCASE,
                c.ATTY_NBR,
                p.IDNPROCEEDING,
                COALESCE(a.asylum_grants, 0) AS asylum_grants,
                COALESCE(a.asylum_decisions, 0) AS asylum_decisions,
                COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, '')) AS nat_code,
                COALESCE(NULLIF(n.NAT_COUNTRY_NAME, ''), NULLIF(n.NAT_NAME, ''),
                         COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, ''))) AS country_name
            FROM canonical_cases c
            LEFT JOIN canonical_proceedings p ON p.IDNCASE = c.IDNCASE
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = p.IDNPROCEEDING
            LEFT JOIN canonical_nationalities n ON n.NAT_CODE = COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, ''))
            WHERE c._current = TRUE
        )
        SELECT
            nat_code,
            COUNT(DISTINCT IDNCASE) AS case_count,
            ROUND(
                SUM(asylum_grants)::DOUBLE
                / NULLIF(SUM(asylum_decisions), 0),
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
        WITH base AS (
            SELECT
                {FY_EXPR} AS fiscal_year,
                NULLIF(
                    TRIM(REPLACE(COALESCE(NULLIF(p.OUTCOME_DESCRIPTION, ''), NULLIF(p.OUTCOME, ''), ''), chr(0), '')),
                    ''
                ) AS cleaned_outcome,
                p.IDNPROCEEDING
            FROM canonical_proceedings p
            WHERE p._current = TRUE
              AND {FY_EXPR} BETWEEN 1990 AND 2027
        )
        SELECT
            fiscal_year,
            CASE
                WHEN cleaned_outcome IS NULL THEN 'Unknown'
                WHEN cleaned_outcome IN ('2', 'D', 'E', 'G', 'O', 'R', 'V', 'X') THEN 'Unknown'
                ELSE cleaned_outcome
            END AS outcome_type,
            COUNT(DISTINCT IDNPROCEEDING) AS case_count
        FROM base
        GROUP BY fiscal_year, outcome_type
        ORDER BY fiscal_year, case_count DESC
    """).df()
    save(df, "case_outcomes")

    annual = (
        df.pivot_table(
            index="fiscal_year",
            columns="outcome_type",
            values="case_count",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .sort_values("fiscal_year", ascending=False)
    )
    annual.columns.name = None
    annual["Total"] = annual.select_dtypes("number").drop(columns=["fiscal_year"], errors="ignore").sum(axis=1)
    save(annual, "case_outcomes_annual")


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
    year = int(str(latest).split("-")[0]) if latest else datetime.now().year
    df = con.execute(f"""
        WITH base AS (
            SELECT
                IDNPROCEEDING,
                CASE
                    WHEN start_date IS NULL THEN NULL
                    WHEN MONTH(start_date) >= 10 THEN YEAR(start_date) + 1
                    ELSE YEAR(start_date)
                END AS start_fy,
                CASE
                    WHEN decision_date IS NULL THEN NULL
                    WHEN MONTH(decision_date) >= 10 THEN YEAR(decision_date) + 1
                    ELSE YEAR(decision_date)
                END AS decision_fy
            FROM (
                SELECT
                    IDNPROCEEDING,
                    COALESCE(
                        TRY_CAST(NULLIF(INPUT_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(OSC_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(HEARING_DATE, '') AS TIMESTAMP)
                    ) AS start_date,
                    TRY_CAST(NULLIF(DECISION_DATE, '') AS TIMESTAMP) AS decision_date
                FROM canonical_proceedings
                WHERE _current = TRUE
            )
            WHERE start_date IS NOT NULL
        ),
        years AS (
            SELECT range AS fiscal_year FROM range(1900, {year + 1})
        ),
        opened AS (
            SELECT start_fy AS fiscal_year, COUNT(DISTINCT IDNPROCEEDING) AS opened_proceedings
            FROM base
            WHERE start_fy BETWEEN 1900 AND {year}
            GROUP BY start_fy
        ),
        completed AS (
            SELECT decision_fy AS fiscal_year, COUNT(DISTINCT IDNPROCEEDING) AS completed_proceedings
            FROM base
            WHERE decision_fy BETWEEN 1900 AND {year}
            GROUP BY decision_fy
        ),
        annual AS (
            SELECT
                y.fiscal_year,
                COALESCE(o.opened_proceedings, 0) AS opened_proceedings,
                COALESCE(c.completed_proceedings, 0) AS completed_proceedings
            FROM years y
            LEFT JOIN opened o ON o.fiscal_year = y.fiscal_year
            LEFT JOIN completed c ON c.fiscal_year = y.fiscal_year
        )
        SELECT
            fiscal_year,
            SUM(opened_proceedings - completed_proceedings) OVER (
                ORDER BY fiscal_year ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::BIGINT AS pending_cases,
            opened_proceedings,
            completed_proceedings
        FROM annual
        QUALIFY fiscal_year BETWEEN 1990 AND {year}
        ORDER BY fiscal_year
    """).df()
    save(df, "backlog_timeline")


def build_case_age_outputs(con: duckdb.DuckDBPyConnection) -> None:
    age = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(p.DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(p.DECISION_DATE AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(p.DECISION_DATE AS TIMESTAMP))
                END AS fiscal_year,
                DATE_DIFF('day',
                    COALESCE(
                        TRY_CAST(NULLIF(p.INPUT_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(p.OSC_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(p.HEARING_DATE, '') AS TIMESTAMP)
                    ),
                    TRY_CAST(NULLIF(p.DECISION_DATE, '') AS TIMESTAMP)
                ) AS age_days,
                CASE WHEN p.CUSTODY IS NOT NULL AND p.CUSTODY NOT IN ('', 'N', '0')
                     THEN TRUE ELSE FALSE END AS detained,
                CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0')
                     THEN TRUE ELSE FALSE END AS represented
            FROM canonical_proceedings p
            LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
            WHERE p._current = TRUE
              AND TRY_CAST(NULLIF(p.DECISION_DATE, '') AS TIMESTAMP) IS NOT NULL
        )
        SELECT
            fiscal_year,
            MEDIAN(age_days) AS median_days,
            QUANTILE_CONT(age_days, 0.25) AS p25_days,
            QUANTILE_CONT(age_days, 0.75) AS p75_days,
            MEDIAN(CASE WHEN detained THEN age_days END) AS detained_median,
            MEDIAN(CASE WHEN NOT detained THEN age_days END) AS nondetained_median,
            MEDIAN(CASE WHEN represented THEN age_days END) AS represented_median,
            MEDIAN(CASE WHEN NOT represented THEN age_days END) AS prose_median,
            NULL::TEXT AS admin
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
          AND age_days BETWEEN 0 AND 20000
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """).df()
    save(age, "case_age_timeline")

    by_court = con.execute("""
        WITH base AS (
            SELECT
                COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
                p.COURT_STATE AS state,
                p.CIRCUIT AS circuit,
                DATE_DIFF('day',
                    COALESCE(
                        TRY_CAST(NULLIF(p.INPUT_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(p.OSC_DATE, '') AS TIMESTAMP),
                        TRY_CAST(NULLIF(p.HEARING_DATE, '') AS TIMESTAMP)
                    ),
                    TRY_CAST(NULLIF(p.DECISION_DATE, '') AS TIMESTAMP)
                ) AS age_days,
                CASE WHEN p.DECISION_DATE IS NULL OR p.DECISION_DATE = '' THEN TRUE ELSE FALSE END AS pending
            FROM canonical_proceedings p
            WHERE p._current = TRUE
              AND p.COURT IS NOT NULL
        )
        SELECT
            court_city,
            state,
            circuit,
            MEDIAN(age_days) AS median_days,
            ROUND(SUM(CASE WHEN pending THEN 1 ELSE 0 END)::DOUBLE / NULLIF(COUNT(*), 0), 4) AS pct_5yr_plus,
            SUM(CASE WHEN pending THEN 1 ELSE 0 END) AS total_pending
        FROM base
        WHERE age_days BETWEEN 0 AND 20000 OR pending
        GROUP BY court_city, state, circuit
        HAVING COUNT(*) >= 100
        ORDER BY total_pending DESC
        LIMIT 100
    """).df()
    save(by_court, "case_age_by_court")

    dist = con.execute("""
        WITH pending AS (
            SELECT DATE_DIFF('day',
                COALESCE(
                    TRY_CAST(NULLIF(p.INPUT_DATE, '') AS TIMESTAMP),
                    TRY_CAST(NULLIF(p.OSC_DATE, '') AS TIMESTAMP),
                    TRY_CAST(NULLIF(p.HEARING_DATE, '') AS TIMESTAMP)
                ),
                current_timestamp
            ) AS age_days
            FROM canonical_proceedings p
            WHERE p._current = TRUE
              AND (p.DECISION_DATE IS NULL OR p.DECISION_DATE = '')
        )
        SELECT age_bucket, COUNT(*) AS count,
            CASE age_bucket
                WHEN 'Under 1 year' THEN '#1e8a50'
                WHEN '1-2 years' THEN '#2980b9'
                WHEN '2-3 years' THEN '#f39c12'
                WHEN '3-5 years' THEN '#e67e22'
                WHEN '5-10 years' THEN '#c0392b'
                ELSE '#8e44ad'
            END AS color
        FROM (
            SELECT CASE
                WHEN age_days < 365 THEN 'Under 1 year'
                WHEN age_days < 730 THEN '1-2 years'
                WHEN age_days < 1095 THEN '2-3 years'
                WHEN age_days < 1825 THEN '3-5 years'
                WHEN age_days < 3650 THEN '5-10 years'
                ELSE 'Over 10 years'
            END AS age_bucket
            FROM pending
            WHERE age_days >= 0
        )
        GROUP BY age_bucket
        ORDER BY MIN(CASE age_bucket
            WHEN 'Under 1 year' THEN 1 WHEN '1-2 years' THEN 2 WHEN '2-3 years' THEN 3
            WHEN '3-5 years' THEN 4 WHEN '5-10 years' THEN 5 ELSE 6 END)
    """).df()
    save(dist, "backlog_age_dist")


def build_removal_outputs(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute(f"""
        WITH classified AS (
            SELECT
                {FY_EXPR} AS fiscal_year,
                COALESCE(NULLIF(p.OUTCOME_DESCRIPTION, ''), p.OUTCOME, 'Unknown') AS outcome_text,
                p.NAT,
                p.IDNPROCEEDING
            FROM canonical_proceedings p
            WHERE p._current = TRUE
              AND {FY_EXPR} BETWEEN 1990 AND 2027
        )
        SELECT
            fiscal_year,
            CASE
                WHEN UPPER(outcome_text) LIKE '%VOL%' THEN 'Voluntary Departure (Departed)'
                WHEN UPPER(outcome_text) LIKE '%REMOV%' OR UPPER(outcome_text) LIKE '%DEPORT%' THEN 'Ordered Removed (IJ)'
                ELSE 'Other EOIR Completion'
            END AS removal_type,
            COUNT(DISTINCT IDNPROCEEDING) AS count,
            NULL::TEXT AS admin
        FROM classified
        WHERE UPPER(outcome_text) LIKE '%VOL%'
           OR UPPER(outcome_text) LIKE '%REMOV%'
           OR UPPER(outcome_text) LIKE '%DEPORT%'
        GROUP BY fiscal_year, removal_type
        ORDER BY fiscal_year, removal_type
    """).df()
    save(df, "removal_orders")

    nat = con.execute("""
        SELECT
            p.NAT AS nat_code,
            COALESCE(NULLIF(n.NAT_COUNTRY_NAME, ''), NULLIF(n.NAT_NAME, ''), p.NAT) AS country,
            COUNT(DISTINCT p.IDNPROCEEDING) AS total_removals,
            0.0 AS expedited_pct
        FROM canonical_proceedings p
        LEFT JOIN canonical_nationalities n ON n.NAT_CODE = p.NAT
        WHERE p._current = TRUE
          AND p.NAT IS NOT NULL
          AND p.NAT != ''
          AND (
              UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%REMOV%'
              OR UPPER(COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '')) LIKE '%DEPORT%'
          )
        GROUP BY p.NAT, country
        ORDER BY total_removals DESC
        LIMIT 100
    """).df()
    save(nat, "removal_by_nationality")


def build_bond_outputs(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(DECISION_DATE AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP))
                END AS fiscal_year,
                IDNBOND,
                DECISION,
                COALESCE(NULLIF(NEW_BOND, 0), NULLIF(INITIAL_BOND, 0)) AS bond_amount
            FROM canonical_bonds
        )
        SELECT
            fiscal_year,
            COUNT(DISTINCT IDNBOND) AS total_hearings,
            COUNT(DISTINCT CASE WHEN bond_amount IS NOT NULL AND bond_amount > 0 THEN IDNBOND END) AS bond_granted,
            COUNT(DISTINCT CASE WHEN bond_amount IS NULL OR bond_amount <= 0 THEN IDNBOND END) AS bond_denied,
            COUNT(DISTINCT CASE WHEN bond_amount IS NOT NULL AND bond_amount > 0 THEN IDNBOND END) AS granted,
            COUNT(DISTINCT CASE WHEN bond_amount IS NULL OR bond_amount <= 0 THEN IDNBOND END) AS denied,
            ROUND(bond_granted::DOUBLE / NULLIF(total_hearings, 0), 4) AS grant_rate,
            MEDIAN(bond_amount) AS median_bond,
            ROUND(bond_denied::DOUBLE / NULLIF(total_hearings, 0), 4) AS detention_rate_post,
            NULL::TEXT AS admin
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        HAVING total_hearings >= 100
        ORDER BY fiscal_year
    """).df()
    save(df, "bond_analytics")


def build_detention_outputs(con: duckdb.DuckDBPyConnection) -> None:
    timeline = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(DATDETAINED AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(DATDETAINED AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(DATDETAINED AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(DATDETAINED AS TIMESTAMP))
                END AS fiscal_year,
                IDNCUSTODY,
                IDNCASE,
                DATE_DIFF('day', TRY_CAST(DATDETAINED AS TIMESTAMP), TRY_CAST(DATRELEASED AS TIMESTAMP)) AS los_days
            FROM canonical_custody_history
            WHERE TRY_CAST(DATDETAINED AS TIMESTAMP) IS NOT NULL
        )
        SELECT
            fiscal_year,
            COUNT(DISTINCT IDNCASE) AS avg_daily_pop,
            NULL::DOUBLE AS detention_beds_funded,
            COUNT(DISTINCT IDNCUSTODY) AS book_ins,
            AVG(CASE WHEN los_days BETWEEN 0 AND 5000 THEN los_days END) AS avg_length_of_stay_days,
            1.0 AS civil_pct,
            0.0 AS criminal_pct,
            COUNT(DISTINCT IDNCASE) AS ice_facilities
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        HAVING book_ins >= 100
        ORDER BY fiscal_year
    """).df()
    save(timeline, "detention_timeline")

    fac = con.execute("""
        WITH case_facilities AS (
            SELECT
                COALESCE(NULLIF(DETENTION_FACILITY_TYPE, ''), 'Unknown') AS facility_type,
                COUNT(DISTINCT IDNCASE) AS cases,
                (SELECT COUNT(DISTINCT IDNCASE)
                 FROM canonical_cases
                 WHERE DETENTION_FACILITY_TYPE IS NOT NULL
                   AND DETENTION_FACILITY_TYPE != '') AS denominator
            FROM canonical_cases
            WHERE DETENTION_FACILITY_TYPE IS NOT NULL
              AND DETENTION_FACILITY_TYPE != ''
            GROUP BY facility_type
        ),
        custody_categories AS (
            SELECT
                CASE CUSTODY
                    WHEN 'D' THEN 'EOIR custody category: detained'
                    WHEN 'R' THEN 'EOIR custody category: released'
                    WHEN 'N' THEN 'EOIR custody category: not detained'
                    ELSE 'EOIR custody category: unknown'
                END AS facility_type,
                COUNT(DISTINCT IDNCASE) AS cases,
                (SELECT COUNT(DISTINCT IDNCASE) FROM canonical_custody_history) AS denominator
            FROM canonical_custody_history
            WHERE CUSTODY IS NOT NULL
              AND CUSTODY != ''
            GROUP BY CUSTODY
        ),
        selected AS (
            SELECT * FROM case_facilities
            UNION ALL
            SELECT * FROM custody_categories
            WHERE NOT EXISTS (SELECT 1 FROM case_facilities)
        )
        SELECT
            facility_type,
            ROUND(cases::DOUBLE / NULLIF(denominator, 0), 4) AS pct_of_pop,
            NULL::DOUBLE AS avg_alos_days,
            NULL::DOUBLE AS avg_daily_cost_usd
        FROM selected
        ORDER BY pct_of_pop DESC
    """).df()
    save(fac, "detention_by_facility")


def build_uac_outputs(con: duckdb.DuckDBPyConnection) -> None:
    metrics = con.execute(f"""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(j.CREATED_ON AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(j.CREATED_ON AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(j.CREATED_ON AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(j.CREATED_ON AS TIMESTAMP))
                END AS fiscal_year,
                j.IDNCASE,
                c.ATTY_NBR,
                p.IDNPROCEEDING,
                COALESCE(NULLIF(c.NAT, ''), NULLIF(p.NAT, '')) AS NAT,
                COALESCE(p.OUTCOME_DESCRIPTION, p.OUTCOME, '') AS outcome_text,
                a.IDNAPPLICATION,
                a.APPLICATION_TYPE,
                a.DECISION
            FROM canonical_juvenile_history j
            LEFT JOIN canonical_cases c ON c.IDNCASE = j.IDNCASE
            LEFT JOIN canonical_proceedings p ON p.IDNPROCEEDING = j.IDNPROCEEDING
            LEFT JOIN canonical_applications a ON a.IDNPROCEEDING = p.IDNPROCEEDING
        )
        SELECT
            fiscal_year,
            COUNT(DISTINCT IDNCASE) AS apprehensions,
            ROUND(
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES} AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END)::DOUBLE
                / NULLIF(COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES} AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END), 0),
                4
            ) AS grant_rate,
            ROUND(COUNT(DISTINCT CASE WHEN ATTY_NBR IS NOT NULL AND ATTY_NBR NOT IN ('', '0') THEN IDNCASE END)::DOUBLE / NULLIF(COUNT(DISTINCT IDNCASE), 0), 4) AS representation_rate,
            ROUND(COUNT(DISTINCT CASE WHEN UPPER(outcome_text) LIKE '%REMOV%' OR UPPER(outcome_text) LIKE '%DEPORT%' THEN IDNPROCEEDING END)::DOUBLE / NULLIF(COUNT(DISTINCT IDNPROCEEDING), 0), 4) AS removal_rate,
            COUNT(DISTINCT CASE WHEN IDNPROCEEDING IS NULL THEN IDNCASE END) AS pending_cases,
            NULL::TEXT AS admin
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """).df()
    save(metrics, "uac_metrics")

    origin = con.execute("""
        SELECT
            'FY' || CAST(fiscal_year AS VARCHAR) AS era,
            NAT AS nat_code,
            COUNT(DISTINCT IDNCASE) AS count
        FROM (
            SELECT
                CASE
                    WHEN TRY_CAST(j.CREATED_ON AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(j.CREATED_ON AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(j.CREATED_ON AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(j.CREATED_ON AS TIMESTAMP))
                END AS fiscal_year,
                j.IDNCASE,
                c.NAT
            FROM canonical_juvenile_history j
            LEFT JOIN canonical_cases c ON c.IDNCASE = j.IDNCASE
        )
        WHERE fiscal_year IS NOT NULL
          AND NAT IS NOT NULL
          AND NAT != ''
        GROUP BY fiscal_year, NAT
        QUALIFY row_number() OVER (PARTITION BY fiscal_year ORDER BY count DESC) <= 15
        ORDER BY fiscal_year, count DESC
    """).df()
    save(origin, "uac_origin")


def build_appeal_outputs(con: duckdb.DuckDBPyConnection) -> None:
    bia = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(COALESCE(NULLIF(BIA_DECISION_DATE, ''), NULLIF(FILED_DATE, '')) AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(COALESCE(NULLIF(BIA_DECISION_DATE, ''), NULLIF(FILED_DATE, '')) AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(COALESCE(NULLIF(BIA_DECISION_DATE, ''), NULLIF(FILED_DATE, '')) AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(COALESCE(NULLIF(BIA_DECISION_DATE, ''), NULLIF(FILED_DATE, '')) AS TIMESTAMP))
                END AS fiscal_year,
                IDNAPPEAL,
                FILED_BY,
                BIA_DECISION,
                BIA_DECISION_TYPE,
                BIA_DECISION_DATE
            FROM canonical_appeals
        )
        SELECT
            fiscal_year,
            COUNT(DISTINCT IDNAPPEAL) AS receipts,
            COUNT(DISTINCT CASE WHEN BIA_DECISION_DATE IS NOT NULL AND BIA_DECISION_DATE != '' THEN IDNAPPEAL END) AS completions,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%DISMISS%' OR UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%AFFIRM%' THEN IDNAPPEAL END) AS dismissed,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%SUSTAIN%' THEN IDNAPPEAL END) AS sustained,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%REMAND%' THEN IDNAPPEAL END) AS remanded,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(FILED_BY, '')) LIKE '%DHS%' OR UPPER(COALESCE(FILED_BY, '')) LIKE '%INS%' THEN IDNAPPEAL END) AS dhs_appeals,
            COUNT(DISTINCT CASE WHEN BIA_DECISION_DATE IS NULL OR BIA_DECISION_DATE = '' THEN IDNAPPEAL END) AS pending,
            NULL::TEXT AS admin
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """).df()
    save(bia, "bia_timeline")

    fed = con.execute("""
        SELECT
            'FED' AS circuit,
            'Federal Courts' AS circuit_name,
            'EOIR federal appeal records' AS key_states,
            COUNT(DISTINCT f.IDNFEDAPPEAL) AS petitions_filed,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(f.FED_DECISION, '')) LIKE '%REMAND%' OR UPPER(COALESCE(f.FED_DECISION, '')) LIKE '%GRANT%' THEN f.IDNFEDAPPEAL END) AS granted_remanded,
            ROUND(granted_remanded::DOUBLE / NULLIF(petitions_filed, 0), 4) AS reversal_rate,
            MEDIAN(DATE_DIFF('day', TRY_CAST(a.BIA_DECISION_DATE AS TIMESTAMP), TRY_CAST(f.REQUESTED_BY_OIL_DATE AS TIMESTAMP))) AS median_days,
            'EOIR does not expose circuit identity in this table' AS notable_case
        FROM canonical_fed_appeals f
        LEFT JOIN canonical_appeals a ON a.IDNAPPEAL = f.IDNAPPEAL
        WHERE f.REQUESTED_BY_OIL_DATE IS NOT NULL
          AND f.REQUESTED_BY_OIL_DATE != ''
    """).df()
    save(fed, "circuit_appeals")


def build_enhancement_trend_outputs(con: duckdb.DuckDBPyConnection) -> None:
    years = range(1990, 2028)
    judge_frames = []
    court_frames = []
    nat_frames = []

    for year in years:
        judge_frames.append(con.execute(f"""
            WITH py AS (
                SELECT
                    p.IDNPROCEEDING,
                    p.IDNCASE,
                    p.IJ_CODE,
                    p.JUDGE_NAME,
                    p.COURT,
                    p.COURT_CITY,
                    p.COURT_STATE,
                    p.CIRCUIT,
                    p.OUTCOME_DESCRIPTION,
                    p.OUTCOME,
                    p.ABSENTIA,
                    c.ATTY_NBR
                FROM canonical_proceedings p
                LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
                WHERE p._current = TRUE
                  AND p.IJ_CODE IS NOT NULL
                  AND p.IJ_CODE != ''
                  AND ({FY_EXPR}) = {year}
            ),
            app_by_proceeding AS (
                SELECT
                    a.IDNPROCEEDING,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END) AS asylum_grants,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {ASYLUM_DECISION_CODES} THEN a.IDNAPPLICATION END) AS asylum_decisions
                FROM canonical_applications a
                JOIN (SELECT DISTINCT IDNPROCEEDING FROM py) ids ON ids.IDNPROCEEDING = a.IDNPROCEEDING
                GROUP BY a.IDNPROCEEDING
            )
            SELECT
                {year} AS fiscal_year,
                py.IJ_CODE AS judge_code,
                COALESCE(NULLIF(py.JUDGE_NAME, ''), py.IJ_CODE) AS judge_name,
                COALESCE(NULLIF(py.COURT_CITY, ''), py.COURT) AS court_city,
                py.COURT_STATE AS state,
                py.CIRCUIT AS circuit,
                COUNT(DISTINCT py.IDNPROCEEDING) AS total_proceedings,
                COUNT(DISTINCT py.IDNCASE) AS total_cases,
                ROUND(SUM(COALESCE(a.asylum_grants, 0))::DOUBLE
                    / NULLIF(SUM(COALESCE(a.asylum_decisions, 0)), 0), 4) AS asylum_grant_rate,
                ROUND(COUNT(DISTINCT CASE WHEN UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%REMOV%' OR UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%DEPORT%' THEN py.IDNPROCEEDING END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNPROCEEDING), 0), 4) AS removal_rate,
                ROUND(COUNT(DISTINCT CASE WHEN py.ABSENTIA IS NOT NULL AND py.ABSENTIA NOT IN ('', 'N', '0') THEN py.IDNPROCEEDING END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNPROCEEDING), 0), 4) AS in_absentia_rate,
                ROUND(COUNT(DISTINCT CASE WHEN py.ATTY_NBR IS NOT NULL AND py.ATTY_NBR NOT IN ('', '0') THEN py.IDNCASE END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNCASE), 0), 4) AS representation_rate
            FROM py
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = py.IDNPROCEEDING
            GROUP BY py.IJ_CODE, py.JUDGE_NAME, py.COURT_CITY, py.COURT, py.COURT_STATE, py.CIRCUIT
            HAVING total_cases >= 20
            ORDER BY total_cases DESC
        """).df())

        court_frames.append(con.execute(f"""
            WITH py AS (
                SELECT
                    p.IDNPROCEEDING,
                    p.IDNCASE,
                    p.COURT,
                    p.COURT_CITY,
                    p.COURT_STATE,
                    p.CIRCUIT,
                    p.DECISION_DATE,
                    p.OUTCOME_DESCRIPTION,
                    p.OUTCOME,
                    p.ABSENTIA,
                    c.ATTY_NBR
                FROM canonical_proceedings p
                LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
                WHERE p._current = TRUE
                  AND p.COURT IS NOT NULL
                  AND p.COURT != ''
                  AND ({FY_EXPR}) = {year}
            ),
            app_by_proceeding AS (
                SELECT
                    a.IDNPROCEEDING,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END) AS asylum_grants,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {ASYLUM_DECISION_CODES} THEN a.IDNAPPLICATION END) AS asylum_decisions
                FROM canonical_applications a
                JOIN (SELECT DISTINCT IDNPROCEEDING FROM py) ids ON ids.IDNPROCEEDING = a.IDNPROCEEDING
                GROUP BY a.IDNPROCEEDING
            )
            SELECT
                {year} AS fiscal_year,
                py.COURT AS court_code,
                COALESCE(NULLIF(py.COURT_CITY, ''), py.COURT) AS court_city,
                py.COURT_STATE AS state,
                py.CIRCUIT AS circuit,
                COUNT(DISTINCT py.IDNPROCEEDING) AS total_proceedings,
                COUNT(DISTINCT py.IDNCASE) AS total_cases,
                COUNT(DISTINCT CASE WHEN py.DECISION_DATE IS NULL OR py.DECISION_DATE = '' THEN py.IDNCASE END) AS pending_cases,
                ROUND(SUM(COALESCE(a.asylum_grants, 0))::DOUBLE
                    / NULLIF(SUM(COALESCE(a.asylum_decisions, 0)), 0), 4) AS asylum_grant_rate,
                ROUND(COUNT(DISTINCT CASE WHEN py.ATTY_NBR IS NOT NULL AND py.ATTY_NBR NOT IN ('', '0') THEN py.IDNCASE END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNCASE), 0), 4) AS representation_rate,
                ROUND(COUNT(DISTINCT CASE WHEN py.ABSENTIA IS NOT NULL AND py.ABSENTIA NOT IN ('', 'N', '0') THEN py.IDNPROCEEDING END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNPROCEEDING), 0), 4) AS in_absentia_rate,
                ROUND(COUNT(DISTINCT CASE WHEN UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%REMOV%' OR UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%DEPORT%' THEN py.IDNPROCEEDING END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNPROCEEDING), 0), 4) AS removal_rate
            FROM py
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = py.IDNPROCEEDING
            GROUP BY py.COURT, py.COURT_CITY, py.COURT_STATE, py.CIRCUIT
            HAVING total_cases >= 20
            ORDER BY total_cases DESC
        """).df())

        nat_frames.append(con.execute(f"""
            WITH py AS (
                SELECT
                    p.IDNPROCEEDING,
                    p.IDNCASE,
                    p.NAT AS proc_nat,
                    p.OUTCOME_DESCRIPTION,
                    p.OUTCOME,
                    c.NAT AS case_nat,
                    c.ATTY_NBR
                FROM canonical_proceedings p
                LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
                WHERE p._current = TRUE
                  AND ({FY_EXPR}) = {year}
            ),
            app_by_proceeding AS (
                SELECT
                    a.IDNPROCEEDING,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {GRANT_CODES} THEN a.IDNAPPLICATION END) AS asylum_grants,
                    COUNT(DISTINCT CASE WHEN a.APPLICATION_TYPE IN {ASYLUM_CODES}
                              AND a.DECISION IN {ASYLUM_DECISION_CODES} THEN a.IDNAPPLICATION END) AS asylum_decisions
                FROM canonical_applications a
                JOIN (SELECT DISTINCT IDNPROCEEDING FROM py) ids ON ids.IDNPROCEEDING = a.IDNPROCEEDING
                GROUP BY a.IDNPROCEEDING
            )
            SELECT
                {year} AS fiscal_year,
                COALESCE(NULLIF(py.proc_nat, ''), NULLIF(py.case_nat, '')) AS nat_code,
                COALESCE(NULLIF(n.NAT_COUNTRY_NAME, ''), NULLIF(n.NAT_NAME, ''), COALESCE(NULLIF(py.proc_nat, ''), NULLIF(py.case_nat, ''))) AS country_name,
                COUNT(DISTINCT py.IDNCASE) AS case_count,
                ROUND(SUM(COALESCE(a.asylum_grants, 0))::DOUBLE
                    / NULLIF(SUM(COALESCE(a.asylum_decisions, 0)), 0), 4) AS asylum_grant_rate,
                ROUND(COUNT(DISTINCT CASE WHEN py.ATTY_NBR IS NOT NULL AND py.ATTY_NBR NOT IN ('', '0') THEN py.IDNCASE END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNCASE), 0), 4) AS representation_rate,
                ROUND(COUNT(DISTINCT CASE WHEN UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%REMOV%' OR UPPER(COALESCE(py.OUTCOME_DESCRIPTION, py.OUTCOME, '')) LIKE '%DEPORT%' THEN py.IDNPROCEEDING END)::DOUBLE
                    / NULLIF(COUNT(DISTINCT py.IDNPROCEEDING), 0), 4) AS removal_rate
            FROM py
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = py.IDNPROCEEDING
            LEFT JOIN canonical_nationalities n ON n.NAT_CODE = COALESCE(NULLIF(py.proc_nat, ''), NULLIF(py.case_nat, ''))
            GROUP BY 2, 3
            HAVING nat_code IS NOT NULL AND nat_code != '' AND case_count >= 50
            ORDER BY case_count DESC
        """).df())

    judge_year = pd.concat(judge_frames, ignore_index=True)
    save(judge_year, "judge_metrics_by_year")

    court_year = pd.concat(court_frames, ignore_index=True)
    save(court_year, "court_metrics_by_year")

    nat_year = pd.concat(nat_frames, ignore_index=True)
    save(nat_year, "nationality_metrics_by_year")


def build_representation_detail_outputs(con: duckdb.DuckDBPyConnection) -> None:
    by_court = con.execute(f"""
        WITH app_by_proceeding AS (
            SELECT
                IDNPROCEEDING,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END) AS asylum_grants,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END) AS asylum_decisions
            FROM canonical_applications
            GROUP BY IDNPROCEEDING
        ),
        base AS (
            SELECT
                COALESCE(NULLIF(p.COURT_CITY, ''), p.COURT) AS court_city,
                p.COURT_STATE AS state,
                p.CIRCUIT AS circuit,
                CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0') THEN TRUE ELSE FALSE END AS represented,
                p.IDNCASE,
                p.IDNPROCEEDING,
                COALESCE(a.asylum_grants, 0) AS asylum_grants,
                COALESCE(a.asylum_decisions, 0) AS asylum_decisions
            FROM canonical_proceedings p
            LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = p.IDNPROCEEDING
            WHERE p._current = TRUE
        )
        SELECT
            court_city,
            state,
            circuit,
            COUNT(DISTINCT IDNCASE) AS cases,
            COUNT(DISTINCT CASE WHEN represented THEN IDNCASE END) AS represented_cases,
            COUNT(DISTINCT CASE WHEN NOT represented THEN IDNCASE END) AS prose_cases,
            ROUND(represented_cases::DOUBLE / NULLIF(cases, 0), 4) AS representation_rate,
            ROUND(SUM(CASE WHEN represented THEN asylum_grants ELSE 0 END)::DOUBLE
                / NULLIF(SUM(CASE WHEN represented THEN asylum_decisions ELSE 0 END), 0), 4) AS represented_grant_rate,
            ROUND(SUM(CASE WHEN NOT represented THEN asylum_grants ELSE 0 END)::DOUBLE
                / NULLIF(SUM(CASE WHEN NOT represented THEN asylum_decisions ELSE 0 END), 0), 4) AS prose_grant_rate
        FROM base
        GROUP BY court_city, state, circuit
        HAVING cases >= 100
        ORDER BY cases DESC
    """).df()
    save(by_court, "representation_by_court")

    by_nat = con.execute(f"""
        WITH app_by_proceeding AS (
            SELECT
                IDNPROCEEDING,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {GRANT_CODES} THEN IDNAPPLICATION END) AS asylum_grants,
                COUNT(DISTINCT CASE WHEN APPLICATION_TYPE IN {ASYLUM_CODES}
                          AND DECISION IN {ASYLUM_DECISION_CODES} THEN IDNAPPLICATION END) AS asylum_decisions
            FROM canonical_applications
            GROUP BY IDNPROCEEDING
        ),
        base AS (
            SELECT
                COALESCE(NULLIF(p.NAT, ''), NULLIF(c.NAT, '')) AS nat_code,
                COALESCE(NULLIF(n.NAT_COUNTRY_NAME, ''), NULLIF(n.NAT_NAME, ''), COALESCE(NULLIF(p.NAT, ''), NULLIF(c.NAT, ''))) AS country_name,
                CASE WHEN c.ATTY_NBR IS NOT NULL AND c.ATTY_NBR NOT IN ('', '0') THEN TRUE ELSE FALSE END AS represented,
                p.IDNCASE,
                COALESCE(a.asylum_grants, 0) AS asylum_grants,
                COALESCE(a.asylum_decisions, 0) AS asylum_decisions
            FROM canonical_proceedings p
            LEFT JOIN canonical_cases c ON c.IDNCASE = p.IDNCASE
            LEFT JOIN app_by_proceeding a ON a.IDNPROCEEDING = p.IDNPROCEEDING
            LEFT JOIN canonical_nationalities n ON n.NAT_CODE = COALESCE(NULLIF(p.NAT, ''), NULLIF(c.NAT, ''))
            WHERE p._current = TRUE
        )
        SELECT
            nat_code,
            country_name,
            COUNT(DISTINCT IDNCASE) AS cases,
            COUNT(DISTINCT CASE WHEN represented THEN IDNCASE END) AS represented_cases,
            COUNT(DISTINCT CASE WHEN NOT represented THEN IDNCASE END) AS prose_cases,
            ROUND(represented_cases::DOUBLE / NULLIF(cases, 0), 4) AS representation_rate,
            ROUND(SUM(CASE WHEN represented THEN asylum_grants ELSE 0 END)::DOUBLE
                / NULLIF(SUM(CASE WHEN represented THEN asylum_decisions ELSE 0 END), 0), 4) AS represented_grant_rate,
            ROUND(SUM(CASE WHEN NOT represented THEN asylum_grants ELSE 0 END)::DOUBLE
                / NULLIF(SUM(CASE WHEN NOT represented THEN asylum_decisions ELSE 0 END), 0), 4) AS prose_grant_rate
        FROM base
        GROUP BY nat_code, country_name
        HAVING nat_code IS NOT NULL AND nat_code != '' AND cases >= 100
        ORDER BY cases DESC
    """).df()
    save(by_nat, "representation_by_nationality")


def build_case_age_detail_outputs(con: duckdb.DuckDBPyConnection) -> None:
    by_type = con.execute("""
        WITH base AS (
            SELECT
                COALESCE(NULLIF(PROCEEDING_TYPE, ''), 'Unknown') AS case_type,
                DATE_DIFF('day',
                    COALESCE(TRY_CAST(NULLIF(INPUT_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(OSC_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(HEARING_DATE, '') AS TIMESTAMP)),
                    TRY_CAST(NULLIF(DECISION_DATE, '') AS TIMESTAMP)
                ) AS completed_age_days,
                DATE_DIFF('day',
                    COALESCE(TRY_CAST(NULLIF(INPUT_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(OSC_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(HEARING_DATE, '') AS TIMESTAMP)),
                    current_timestamp
                ) AS pending_age_days,
                CASE WHEN DECISION_DATE IS NULL OR DECISION_DATE = '' THEN TRUE ELSE FALSE END AS pending,
                IDNPROCEEDING
            FROM canonical_proceedings
            WHERE _current = TRUE
        )
        SELECT
            case_type,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings,
            COUNT(DISTINCT CASE WHEN pending THEN IDNPROCEEDING END) AS pending_proceedings,
            MEDIAN(CASE WHEN NOT pending AND completed_age_days BETWEEN 0 AND 20000 THEN completed_age_days END) AS completed_median_days,
            QUANTILE_CONT(CASE WHEN NOT pending AND completed_age_days BETWEEN 0 AND 20000 THEN completed_age_days END, 0.75) AS completed_p75_days,
            MEDIAN(CASE WHEN pending AND pending_age_days BETWEEN 0 AND 30000 THEN pending_age_days END) AS pending_median_days
        FROM base
        GROUP BY case_type
        HAVING proceedings >= 100
        ORDER BY proceedings DESC
    """).df()
    save(by_type, "case_age_by_case_type")

    by_judge = con.execute("""
        WITH base AS (
            SELECT
                IJ_CODE AS judge_code,
                COALESCE(NULLIF(JUDGE_NAME, ''), IJ_CODE) AS judge_name,
                COALESCE(NULLIF(COURT_CITY, ''), COURT) AS court_city,
                CIRCUIT AS circuit,
                DATE_DIFF('day',
                    COALESCE(TRY_CAST(NULLIF(INPUT_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(OSC_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(HEARING_DATE, '') AS TIMESTAMP)),
                    TRY_CAST(NULLIF(DECISION_DATE, '') AS TIMESTAMP)
                ) AS completed_age_days,
                DATE_DIFF('day',
                    COALESCE(TRY_CAST(NULLIF(INPUT_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(OSC_DATE, '') AS TIMESTAMP),
                             TRY_CAST(NULLIF(HEARING_DATE, '') AS TIMESTAMP)),
                    current_timestamp
                ) AS pending_age_days,
                CASE WHEN DECISION_DATE IS NULL OR DECISION_DATE = '' THEN TRUE ELSE FALSE END AS pending,
                IDNPROCEEDING
            FROM canonical_proceedings
            WHERE _current = TRUE
              AND IJ_CODE IS NOT NULL
              AND IJ_CODE != ''
        )
        SELECT
            judge_code,
            judge_name,
            court_city,
            circuit,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings,
            COUNT(DISTINCT CASE WHEN pending THEN IDNPROCEEDING END) AS pending_proceedings,
            MEDIAN(CASE WHEN NOT pending AND completed_age_days BETWEEN 0 AND 20000 THEN completed_age_days END) AS completed_median_days,
            MEDIAN(CASE WHEN pending AND pending_age_days BETWEEN 0 AND 30000 THEN pending_age_days END) AS pending_median_days
        FROM base
        GROUP BY judge_code, judge_name, court_city, circuit
        HAVING proceedings >= 100
        ORDER BY proceedings DESC
    """).df()
    save(by_judge, "case_age_by_judge")


def build_bond_detail_outputs(con: duckdb.DuckDBPyConnection) -> None:
    base_sql = """
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(DECISION_DATE AS TIMESTAMP)) >= 10 THEN YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP))
                END AS fiscal_year,
                IDNBOND,
                IJ_CODE,
                COALESCE(NULLIF(COURT_CITY, ''), COURT) AS court_city,
                COALESCE(NULLIF(NEW_BOND, 0), NULLIF(INITIAL_BOND, 0)) AS bond_amount
            FROM canonical_bonds
        )
    """
    by_year = con.execute(base_sql + """
        SELECT
            fiscal_year,
            COUNT(DISTINCT IDNBOND) AS bond_hearings,
            COUNT(DISTINCT CASE WHEN bond_amount IS NOT NULL AND bond_amount > 0 THEN IDNBOND END) AS granted,
            COUNT(DISTINCT CASE WHEN bond_amount IS NULL OR bond_amount <= 0 THEN IDNBOND END) AS denied_or_no_amount,
            ROUND(granted::DOUBLE / NULLIF(bond_hearings, 0), 4) AS grant_rate,
            MEDIAN(bond_amount) AS median_bond,
            QUANTILE_CONT(bond_amount, 0.25) AS p25_bond,
            QUANTILE_CONT(bond_amount, 0.75) AS p75_bond
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year
        HAVING bond_hearings >= 100
        ORDER BY fiscal_year
    """).df()
    save(by_year, "bond_by_year")

    by_court = con.execute(base_sql + """
        SELECT
            court_city,
            COUNT(DISTINCT IDNBOND) AS bond_hearings,
            COUNT(DISTINCT CASE WHEN bond_amount IS NOT NULL AND bond_amount > 0 THEN IDNBOND END) AS granted,
            ROUND(granted::DOUBLE / NULLIF(bond_hearings, 0), 4) AS grant_rate,
            MEDIAN(bond_amount) AS median_bond,
            QUANTILE_CONT(bond_amount, 0.75) AS p75_bond
        FROM base
        GROUP BY court_city
        HAVING bond_hearings >= 50
        ORDER BY bond_hearings DESC
    """).df()
    save(by_court, "bond_by_court")

    by_judge = con.execute(base_sql + """
        SELECT
            IJ_CODE AS judge_code,
            COUNT(DISTINCT IDNBOND) AS bond_hearings,
            COUNT(DISTINCT CASE WHEN bond_amount IS NOT NULL AND bond_amount > 0 THEN IDNBOND END) AS granted,
            ROUND(granted::DOUBLE / NULLIF(bond_hearings, 0), 4) AS grant_rate,
            MEDIAN(bond_amount) AS median_bond,
            QUANTILE_CONT(bond_amount, 0.75) AS p75_bond
        FROM base
        WHERE IJ_CODE IS NOT NULL AND IJ_CODE != ''
        GROUP BY IJ_CODE
        HAVING bond_hearings >= 50
        ORDER BY bond_hearings DESC
    """).df()
    save(by_judge, "bond_by_judge")


def build_extended_event_outputs(con: duckdb.DuckDBPyConnection) -> None:
    custody = con.execute("""
        WITH ordered AS (
            SELECT
                IDNCASE,
                CUSTODY,
                DATDETAINED,
                DATRELEASED,
                FIRST_VALUE(CUSTODY) OVER (PARTITION BY IDNCASE ORDER BY TRY_CAST(NULLIF(DATDETAINED, '') AS TIMESTAMP) NULLS LAST, IDNCUSTODY) AS first_custody,
                LAST_VALUE(CUSTODY) OVER (PARTITION BY IDNCASE ORDER BY TRY_CAST(NULLIF(DATDETAINED, '') AS TIMESTAMP) NULLS LAST, IDNCUSTODY ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_custody,
                DATE_DIFF('day', TRY_CAST(NULLIF(DATDETAINED, '') AS TIMESTAMP), TRY_CAST(NULLIF(DATRELEASED, '') AS TIMESTAMP)) AS detention_days
            FROM canonical_custody_history
        )
        SELECT
            COALESCE(first_custody, 'Unknown') AS first_custody,
            COALESCE(last_custody, 'Unknown') AS last_custody,
            COUNT(DISTINCT IDNCASE) AS cases,
            AVG(CASE WHEN detention_days BETWEEN 0 AND 5000 THEN detention_days END) AS avg_recorded_detention_days
        FROM ordered
        GROUP BY first_custody, last_custody
        ORDER BY cases DESC
    """).df()
    save(custody, "custody_transitions")

    appeals = con.execute("""
        SELECT
            COALESCE(NULLIF(APPEAL_CATEGORY, ''), 'Unknown') AS appeal_category,
            COALESCE(NULLIF(APPEAL_TYPE, ''), 'Unknown') AS appeal_type,
            COALESCE(NULLIF(FILED_BY, ''), 'Unknown') AS filed_by,
            COALESCE(NULLIF(BIA_DECISION, ''), NULLIF(BIA_DECISION_TYPE, ''), 'Pending/Unknown') AS decision_group,
            COUNT(DISTINCT IDNAPPEAL) AS appeals,
            COUNT(DISTINCT CASE WHEN BIA_DECISION_DATE IS NOT NULL AND BIA_DECISION_DATE != '' THEN IDNAPPEAL END) AS completed,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%REMAND%' THEN IDNAPPEAL END) AS remanded,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%SUSTAIN%' THEN IDNAPPEAL END) AS sustained,
            COUNT(DISTINCT CASE WHEN UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%DISMISS%' OR UPPER(COALESCE(BIA_DECISION, BIA_DECISION_TYPE, '')) LIKE '%AFFIRM%' THEN IDNAPPEAL END) AS dismissed_or_affirmed
        FROM canonical_appeals
        GROUP BY appeal_category, appeal_type, filed_by, decision_group
        HAVING appeals >= 20
        ORDER BY appeals DESC
    """).df()
    save(appeals, "appeal_outcomes_by_type")

    schedule = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(ADJ_DATE AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(ADJ_DATE AS TIMESTAMP)) >= 10 THEN YEAR(TRY_CAST(ADJ_DATE AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(ADJ_DATE AS TIMESTAMP))
                END AS fiscal_year,
                HEARING_LOC_CODE,
                SCHEDULE_TYPE,
                CAL_TYPE,
                ADJ_RSN,
                TRY_CAST(ADJ_ELAP_DAYS AS DOUBLE) AS elapsed_days,
                IDNSCHEDULE,
                IDNPROCEEDING
            FROM canonical_schedules
        )
        SELECT
            fiscal_year,
            COALESCE(NULLIF(HEARING_LOC_CODE, ''), 'Unknown') AS hearing_loc_code,
            COALESCE(NULLIF(SCHEDULE_TYPE, ''), 'Unknown') AS schedule_type,
            COALESCE(NULLIF(CAL_TYPE, ''), 'Unknown') AS calendar_type,
            COUNT(DISTINCT IDNSCHEDULE) AS hearings,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings,
            AVG(CASE WHEN elapsed_days BETWEEN 0 AND 5000 THEN elapsed_days END) AS avg_elapsed_days
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year, hearing_loc_code, schedule_type, calendar_type
        HAVING hearings >= 20
        ORDER BY fiscal_year, hearings DESC
    """).df()
    save(schedule, "hearing_schedule_metrics")

    continuance = con.execute("""
        SELECT
            COALESCE(NULLIF(ADJ_RSN, ''), 'Unknown') AS adjournment_reason,
            COUNT(DISTINCT IDNSCHEDULE) AS hearings,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings,
            AVG(CASE WHEN TRY_CAST(ADJ_ELAP_DAYS AS DOUBLE) BETWEEN 0 AND 5000 THEN TRY_CAST(ADJ_ELAP_DAYS AS DOUBLE) END) AS avg_elapsed_days
        FROM canonical_schedules
        GROUP BY adjournment_reason
        HAVING hearings >= 100
        ORDER BY hearings DESC
    """).df()
    save(continuance, "continuance_metrics")

    charges = con.execute("""
        SELECT
            COALESCE(NULLIF(CHARGE, ''), 'Unknown') AS charge,
            COALESCE(NULLIF(CHARGE_STATUS, ''), 'Unknown') AS charge_status,
            COUNT(DISTINCT IDNCHARGE) AS charge_records,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings,
            COUNT(DISTINCT IDNCASE) AS cases
        FROM canonical_charges
        GROUP BY charge, charge_status
        HAVING charge_records >= 100
        ORDER BY charge_records DESC
    """).df()
    save(charges, "charge_analysis")

    charge_outcomes = con.execute("""
        WITH charge_proc AS MATERIALIZED (
            SELECT
                COALESCE(NULLIF(CHARGE, ''), 'Unknown') AS charge,
                IDNPROCEEDING
            FROM canonical_charges
            WHERE IDNPROCEEDING IS NOT NULL
              AND IDNPROCEEDING != ''
            GROUP BY 1, 2
        ),
        proc_outcomes AS MATERIALIZED (
            SELECT
                IDNPROCEEDING,
                COALESCE(NULLIF(OUTCOME_DESCRIPTION, ''), NULLIF(OUTCOME, ''), 'Unknown') AS outcome
            FROM canonical_proceedings
            WHERE IDNPROCEEDING IS NOT NULL
              AND IDNPROCEEDING != ''
        )
        SELECT
            cp.charge,
            COALESCE(po.outcome, 'Unknown') AS outcome,
            COUNT(*) AS proceedings
        FROM charge_proc cp
        LEFT JOIN proc_outcomes po ON po.IDNPROCEEDING = cp.IDNPROCEEDING
        GROUP BY 1, 2
        HAVING proceedings >= 100
        ORDER BY proceedings DESC
    """).df()
    save(charge_outcomes, "charge_outcomes")

    motions = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(MOTION_RECD_DATE AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(MOTION_RECD_DATE AS TIMESTAMP)) >= 10 THEN YEAR(TRY_CAST(MOTION_RECD_DATE AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(MOTION_RECD_DATE AS TIMESTAMP))
                END AS fiscal_year,
                COALESCE(NULLIF(FILING_PARTY, ''), 'Unknown') AS filing_party,
                COALESCE(NULLIF(FILING_METHOD, ''), 'Unknown') AS filing_method,
                COALESCE(NULLIF(DECISION, ''), 'Pending/Unknown') AS decision,
                IDNMOTION,
                IDNPROCEEDING
            FROM canonical_motions
        )
        SELECT
            fiscal_year,
            filing_party,
            filing_method,
            decision,
            COUNT(DISTINCT IDNMOTION) AS motions,
            COUNT(DISTINCT IDNPROCEEDING) AS proceedings
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year, filing_party, filing_method, decision
        HAVING motions >= 20
        ORDER BY fiscal_year, motions DESC
    """).df()
    save(motions, "motion_activity")

    reps = con.execute("""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRY_CAST(COALESCE(NULLIF(ASSIGNED_DATE, ''), NULLIF(E28_DATE, ''), NULLIF(E27_DATE, '')) AS TIMESTAMP) IS NULL THEN NULL
                    WHEN MONTH(TRY_CAST(COALESCE(NULLIF(ASSIGNED_DATE, ''), NULLIF(E28_DATE, ''), NULLIF(E27_DATE, '')) AS TIMESTAMP)) >= 10
                        THEN YEAR(TRY_CAST(COALESCE(NULLIF(ASSIGNED_DATE, ''), NULLIF(E28_DATE, ''), NULLIF(E27_DATE, '')) AS TIMESTAMP)) + 1
                    ELSE YEAR(TRY_CAST(COALESCE(NULLIF(ASSIGNED_DATE, ''), NULLIF(E28_DATE, ''), NULLIF(E27_DATE, '')) AS TIMESTAMP))
                END AS fiscal_year,
                COALESCE(NULLIF(ATTY_LEVEL, ''), 'Unknown') AS atty_level,
                COALESCE(NULLIF(ATTY_TYPE, ''), 'Unknown') AS atty_type,
                PRIME_ATTORNEY,
                IDNREPASSIGNMENT,
                IDNCASE
            FROM canonical_rep_assignments
        )
        SELECT
            fiscal_year,
            atty_level,
            atty_type,
            COUNT(DISTINCT IDNREPASSIGNMENT) AS assignments,
            COUNT(DISTINCT IDNCASE) AS cases,
            COUNT(DISTINCT CASE WHEN PRIME_ATTORNEY IN ('1', 'true', 'True', 'Y') THEN IDNREPASSIGNMENT END) AS prime_assignments
        FROM base
        WHERE fiscal_year BETWEEN 1990 AND 2027
        GROUP BY fiscal_year, atty_level, atty_type
        HAVING assignments >= 20
        ORDER BY fiscal_year, assignments DESC
    """).df()
    save(reps, "representation_details")


def build_quality_and_snapshot_outputs(con: duckdb.DuckDBPyConnection) -> None:
    tables = [
        ("canonical_cases", "IDNCASE"),
        ("canonical_proceedings", "IDNPROCEEDING"),
        ("canonical_applications", "IDNAPPLICATION"),
        ("canonical_bonds", "IDNBOND"),
        ("canonical_custody_history", "IDNCUSTODY"),
        ("canonical_juvenile_history", "IDNJUVENILEHISTORY"),
        ("canonical_appeals", "IDNAPPEAL"),
        ("canonical_fed_appeals", "IDNFEDAPPEAL"),
        ("canonical_schedules", "IDNSCHEDULE"),
        ("canonical_charges", "IDNCHARGE"),
        ("canonical_rep_assignments", "IDNREPASSIGNMENT"),
        ("canonical_motions", "IDNMOTION"),
    ]
    rows = []
    for table, key in tables:
        if table not in {r[0] for r in con.execute("SHOW TABLES").fetchall()}:
            continue
        row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        bad_keys = con.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE {key} IS NULL
               OR NULLIF(TRIM(REPLACE({key}, chr(0), '')), '') IS NULL
        """).fetchone()[0]
        rows.append({
            "table_name": table,
            "row_count": row_count,
            "blank_or_null_key_count": bad_keys,
            "blank_or_null_key_rate": round(bad_keys / row_count, 6) if row_count else 0,
        })
    save(pd.DataFrame(rows), "data_quality_summary")

    snapshot = pd.DataFrame([{
        "release_tag": con.execute("SELECT MAX(_last_seen_release) FROM canonical_cases").fetchone()[0],
        "cases": con.execute("SELECT COUNT(*) FROM canonical_cases").fetchone()[0],
        "proceedings": con.execute("SELECT COUNT(*) FROM canonical_proceedings").fetchone()[0],
        "applications": con.execute("SELECT COUNT(*) FROM canonical_applications").fetchone()[0],
        "bonds": con.execute("SELECT COUNT(*) FROM canonical_bonds").fetchone()[0],
        "custody_history": con.execute("SELECT COUNT(*) FROM canonical_custody_history").fetchone()[0],
        "schedules": con.execute("SELECT COUNT(*) FROM canonical_schedules").fetchone()[0],
        "charges": con.execute("SELECT COUNT(*) FROM canonical_charges").fetchone()[0],
        "motions": con.execute("SELECT COUNT(*) FROM canonical_motions").fetchone()[0],
        "note": "Single EOIR release snapshot. True monthly history requires preserving and comparing repeated monthly releases.",
    }])
    save(snapshot, "release_snapshot_tracking")


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


def run_all(db_path: Path | None = None) -> None:
    log.info("Starting Gold layer aggregation...")
    con = get_con(db_path)
    build_judge_metrics(con)
    build_court_metrics(con)
    build_nationality_metrics(con)
    build_case_outcomes(con)
    build_representation_gap(con)
    build_policy_trends(con)
    build_in_absentia(con)
    build_backlog_timeline(con)
    build_case_age_outputs(con)
    build_removal_outputs(con)
    build_bond_outputs(con)
    build_detention_outputs(con)
    build_uac_outputs(con)
    build_appeal_outputs(con)
    build_enhancement_trend_outputs(con)
    build_representation_detail_outputs(con)
    build_case_age_detail_outputs(con)
    build_bond_detail_outputs(con)
    build_extended_event_outputs(con)
    build_quality_and_snapshot_outputs(con)
    write_pipeline_status(con)
    con.close()
    log.info("Gold aggregation complete. Data written to /data/")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build Gold Parquet outputs from canonical DuckDB")
    parser.add_argument(
        "--canonical-db",
        default=None,
        help="Optional canonical DuckDB path. Defaults to silver/canonical.duckdb.",
    )
    args = parser.parse_args()
    run_all(Path(args.canonical_db) if args.canonical_db else None)
