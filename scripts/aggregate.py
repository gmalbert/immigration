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
    return duckdb.connect(str(canonical_db), read_only=True)


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
            COALESCE(cleaned_outcome, 'Unknown') AS outcome_type,
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
    pending = con.execute("""
        SELECT COUNT(DISTINCT p.IDNCASE)
        FROM canonical_proceedings p
        WHERE p._current = TRUE
          AND (p.DECISION_DATE IS NULL OR p.DECISION_DATE = '')
    """).fetchone()[0]
    year = int(str(latest).split("-")[0]) if latest else datetime.now().year
    save(pd.DataFrame([{"fiscal_year": year, "pending_cases": pending}]), "backlog_timeline")


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
