"""
scripts/canonical.py - Build and maintain the Silver-layer canonical dataset.

The canonical dataset never physically deletes records. Records absent from a
new monthly EOIR release are marked in provenance metadata so downstream
analytics can distinguish current rows from historical rows.

Usage:
    python scripts/canonical.py --release 2026-06
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
SILVER_DIR = ROOT / "silver"
CANONICAL_DB = SILVER_DIR / "canonical.duckdb"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_canonical_con(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path or CANONICAL_DB))
    # The EOIR release is large enough that a conservative local profile is
    # more reliable on ordinary laptops than DuckDB's default parallelism.
    con.execute("PRAGMA threads=1")
    con.execute("PRAGMA memory_limit='4GB'")
    con.execute("PRAGMA preserve_insertion_order=false")
    return con


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return table_name in {row[0] for row in con.execute("SHOW TABLES").fetchall()}


def _attach_release(
    con: duckdb.DuckDBPyConnection,
    release_tag: str,
    ingest_db: Path | None = None,
) -> None:
    release_db = ingest_db or SILVER_DIR / f"{release_tag}.duckdb"
    if not release_db.exists():
        raise FileNotFoundError(
            f"Ingest DB not found: {release_db}\nRun scripts/ingest.py first."
        )
    con.execute(f"ATTACH '{release_db.as_posix()}' AS rel (READ_ONLY)")


def init_canonical(con: duckdb.DuckDBPyConnection) -> None:
    """Create canonical tables if they do not exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_cases (
            IDNCASE                TEXT PRIMARY KEY,
            ANUMBER                TEXT,
            NAT                    TEXT,
            LANG                   TEXT,
            GENDER                 TEXT,
            INPUT_DATE             TEXT,
            COMP_DATE              TEXT,
            NTA_DATE               TEXT,
            CUSTDY                 TEXT,
            ATTY_NBR               TEXT,
            CASE_TYPE              TEXT,
            LATEST_HEARING         TEXT,
            DATE_DETAINED          TEXT,
            DATE_RELEASED          TEXT,
            DETENTION_DATE         TEXT,
            DETENTION_LOCATION     TEXT,
            DETENTION_FACILITY_TYPE TEXT,
            _first_seen_release    TEXT NOT NULL,
            _last_seen_release     TEXT NOT NULL,
            _ever_deleted          BOOLEAN DEFAULT FALSE,
            _deletion_releases     TEXT,
            _current               BOOLEAN DEFAULT TRUE
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_proceedings (
            IDNPROCEEDING          TEXT PRIMARY KEY,
            IDNCASE                TEXT,
            IJ_CODE                TEXT,
            JUDGE_NAME             TEXT,
            COURT                  TEXT,
            COURT_CITY             TEXT,
            COURT_STATE            TEXT,
            CIRCUIT                TEXT,
            PROCEEDING_TYPE        TEXT,
            OSC_DATE               TEXT,
            INPUT_DATE             TEXT,
            HEARING_DATE           TEXT,
            OUTCOME                TEXT,
            OUTCOME_DESCRIPTION    TEXT,
            DECISION_DATE          TEXT,
            APPEAL_FILED           TEXT,
            ABSENTIA               TEXT,
            CUSTODY                TEXT,
            NAT                    TEXT,
            LANG                   TEXT,
            DATE_DETAINED          TEXT,
            DATE_RELEASED          TEXT,
            _first_seen_release    TEXT NOT NULL,
            _last_seen_release     TEXT NOT NULL,
            _ever_deleted          BOOLEAN DEFAULT FALSE,
            _deletion_releases     TEXT,
            _current               BOOLEAN DEFAULT TRUE
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_applications (
            IDNAPPLICATION         TEXT PRIMARY KEY,
            IDNPROCEEDING          TEXT,
            IDNCASE                TEXT,
            APPLICATION_TYPE       TEXT,
            FILED_DATE             TEXT,
            DECISION_DATE          TEXT,
            DECISION               TEXT,
            _first_seen_release    TEXT NOT NULL,
            _last_seen_release     TEXT NOT NULL,
            _ever_deleted          BOOLEAN DEFAULT FALSE,
            _deletion_releases     TEXT,
            _current               BOOLEAN DEFAULT TRUE
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_nationalities (
            NAT_CODE               TEXT PRIMARY KEY,
            NAT_NAME               TEXT,
            NAT_COUNTRY_NAME       TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_bonds (
            IDNBOND                TEXT PRIMARY KEY,
            IDNPROCEEDING          TEXT,
            IDNCASE                TEXT,
            IJ_CODE                TEXT,
            COURT                  TEXT,
            COURT_CITY             TEXT,
            DECISION               TEXT,
            DECISION_DATE          TEXT,
            INITIAL_BOND           DOUBLE,
            NEW_BOND               DOUBLE,
            BOND_TYPE              TEXT,
            REQUEST_DATE           TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_custody_history (
            IDNCUSTODY             TEXT PRIMARY KEY,
            IDNCASE                TEXT,
            CUSTODY                TEXT,
            DATDETAINED            TEXT,
            DATRELEASED            TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_juvenile_history (
            IDNJUVENILEHISTORY     TEXT PRIMARY KEY,
            IDNCASE                TEXT,
            IDNPROCEEDING          TEXT,
            IDNJUVENILE            TEXT,
            CREATED_ON             TEXT,
            MODIFIED_ON            TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_appeals (
            IDNAPPEAL              TEXT PRIMARY KEY,
            IDNCASE                TEXT,
            IDNPROCEEDING          TEXT,
            APPEAL_CATEGORY        TEXT,
            APPEAL_TYPE            TEXT,
            FILED_DATE             TEXT,
            FILED_BY               TEXT,
            BIA_DECISION_DATE      TEXT,
            BIA_DECISION           TEXT,
            BIA_DECISION_TYPE      TEXT,
            CASE_TYPE              TEXT,
            NAT                    TEXT,
            CUSTODY                TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_fed_appeals (
            IDNFEDAPPEAL           TEXT PRIMARY KEY,
            IDNAPPEAL              TEXT,
            REQUESTED_BY_OIL_DATE  TEXT,
            FED_DECISION_DATE      TEXT,
            FED_DECISION           TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_three_member_referrals (
            IDNREFERRAL            TEXT PRIMARY KEY,
            IDNAPPEAL              TEXT,
            REFERRED_DATE          TEXT,
            REMOVED_DATE           TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_schedules (
            IDNSCHEDULE            TEXT,
            IDNPROCEEDING          TEXT,
            IDNCASE                TEXT,
            HEARING_LOC_CODE       TEXT,
            BASE_CITY_CODE         TEXT,
            IJ_CODE                TEXT,
            ADJ_DATE               TEXT,
            ADJ_RSN                TEXT,
            ADJ_MEDIUM             TEXT,
            ADJ_ELAP_DAYS          TEXT,
            SCHEDULE_TYPE          TEXT,
            CAL_TYPE               TEXT,
            NOTICE_CODE            TEXT,
            ATTORNEY_ID            TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_charges (
            IDNCHARGE              TEXT,
            IDNPROCEEDING          TEXT,
            IDNCASE                TEXT,
            CHARGE                 TEXT,
            CHARGE_STATUS          TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_rep_assignments (
            IDNREPASSIGNMENT       TEXT,
            IDNCASE                TEXT,
            ATTY_LEVEL             TEXT,
            ATTY_TYPE              TEXT,
            PARENT_TABLE           TEXT,
            PARENT_IDN             TEXT,
            BASE_CITY_CODE         TEXT,
            ASSIGNED_DATE          TEXT,
            E27_DATE               TEXT,
            E28_DATE               TEXT,
            PRIME_ATTORNEY         TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_attorneys (
            ATTORNEY_ID            TEXT PRIMARY KEY,
            OLD_ATTORNEY_ID        TEXT,
            BASE_CITY_CODE         TEXT,
            ACTIVE                 TEXT,
            SOURCE_FLAG            TEXT,
            CREATED_ON             TEXT,
            MODIFIED_ON            TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS canonical_motions (
            IDNMOTION              TEXT,
            IDNPROCEEDING          TEXT,
            IDNCASE                TEXT,
            HEARING_LOC_CODE       TEXT,
            BASE_CITY_CODE         TEXT,
            IJ_CODE                TEXT,
            MOTION_RECD_DATE       TEXT,
            MOTION_DUE_DATE        TEXT,
            RESP_DUE_DATE          TEXT,
            DECISION               TEXT,
            COMP_DATE              TEXT,
            FILING_PARTY           TEXT,
            FILING_METHOD          TEXT,
            STAY_GRANT             TEXT,
            JURISDICTION           TEXT,
            _last_seen_release     TEXT NOT NULL
        )
    """)

    # Older canonical DBs may exist from earlier pipeline versions.
    for table_name, columns in {
        "canonical_cases": {
            "LATEST_HEARING": "TEXT",
            "DATE_DETAINED": "TEXT",
            "DATE_RELEASED": "TEXT",
            "DETENTION_DATE": "TEXT",
            "DETENTION_FACILITY_TYPE": "TEXT",
        },
        "canonical_proceedings": {
            "OSC_DATE": "TEXT",
            "INPUT_DATE": "TEXT",
            "HEARING_DATE": "TEXT",
            "DATE_DETAINED": "TEXT",
            "DATE_RELEASED": "TEXT",
        },
    }.items():
        for col, col_type in columns.items():
            con.execute(f"ALTER TABLE {qident(table_name)} ADD COLUMN IF NOT EXISTS {qident(col)} {col_type}")

    con.execute("""
        CREATE TABLE IF NOT EXISTS _release_log (
            release_tag            TEXT PRIMARY KEY,
            ingested_at            TIMESTAMP DEFAULT current_timestamp,
            case_count             BIGINT,
            proceeding_count       BIGINT,
            application_count      BIGINT,
            deletions_flagged      BIGINT
        )
    """)
    con.execute("CHECKPOINT")


def _create_lookup_temp_tables(con: duckdb.DuckDBPyConnection) -> None:
    rel_tables = {row[0] for row in con.execute("SHOW TABLES FROM rel").fetchall()}

    if "tblLookupHloc" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _court_lookup AS
            SELECT
                HEARING_LOC_CODE::TEXT AS COURT,
                COALESCE(NULLIF(HEARING_LOC_NAME, ''), NULLIF(HEARING_CITY, ''), HEARING_LOC_CODE)::TEXT AS COURT_CITY,
                HEARING_STATE::TEXT AS COURT_STATE,
                CASE TRY_CAST(CircuitCourt AS INTEGER)
                    WHEN 1 THEN '1st'
                    WHEN 2 THEN '2nd'
                    WHEN 3 THEN '3rd'
                    ELSE TRY_CAST(CircuitCourt AS VARCHAR) || 'th'
                END AS CIRCUIT
            FROM rel.tblLookupHloc
            QUALIFY row_number() OVER (PARTITION BY HEARING_LOC_CODE ORDER BY blnActive DESC NULLS LAST) = 1
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _court_lookup (
                COURT TEXT, COURT_CITY TEXT, COURT_STATE TEXT, CIRCUIT TEXT
            )
        """)

    if "tblLookupJudge" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _judge_lookup AS
            SELECT
                JUDGE_CODE::TEXT AS IJ_CODE,
                JUDGE_NAME::TEXT AS JUDGE_NAME
            FROM rel.tblLookupJudge
            QUALIFY row_number() OVER (PARTITION BY JUDGE_CODE ORDER BY blnActive DESC NULLS LAST) = 1
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _judge_lookup (IJ_CODE TEXT, JUDGE_NAME TEXT)
        """)

    if "tblLookupCourtDecision" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _decision_lookup AS
            SELECT
                strCaseType::TEXT AS CASE_TYPE,
                strDecCode::TEXT AS OUTCOME,
                strDecDescription::TEXT AS OUTCOME_DESCRIPTION,
                strFinalDisposition::TEXT AS FINAL_DISPOSITION
            FROM rel.tblLookupCourtDecision
            QUALIFY row_number() OVER (
                PARTITION BY strCaseType, strDecCode
                ORDER BY blnActive DESC NULLS LAST
            ) = 1
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _decision_lookup (
                CASE_TYPE TEXT, OUTCOME TEXT, OUTCOME_DESCRIPTION TEXT, FINAL_DISPOSITION TEXT
            )
        """)


def _stage_release(con: duckdb.DuckDBPyConnection) -> None:
    """Translate June 2026 EOIR tables into stable canonical temp tables."""
    rel_tables = {row[0] for row in con.execute("SHOW TABLES FROM rel").fetchall()}
    required = {"A_TblCase", "B_TblProceeding", "E_TblApplication"}
    missing = required - rel_tables
    if missing:
        raise RuntimeError(f"Ingest DB missing required tables: {', '.join(sorted(missing))}")

    _create_lookup_temp_tables(con)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE _new_cases AS
        SELECT
            IDNCASE::TEXT AS IDNCASE,
            NULL::TEXT AS ANUMBER,
            NAT::TEXT AS NAT,
            LANG::TEXT AS LANG,
            Sex::TEXT AS GENDER,
            NULL::TEXT AS INPUT_DATE,
            NULL::TEXT AS COMP_DATE,
            NULL::TEXT AS NTA_DATE,
            CUSTODY::TEXT AS CUSTDY,
            ATTY_NBR::TEXT AS ATTY_NBR,
            CASE_TYPE::TEXT AS CASE_TYPE,
            LATEST_HEARING::TEXT AS LATEST_HEARING,
            DATE_DETAINED::TEXT AS DATE_DETAINED,
            DATE_RELEASED::TEXT AS DATE_RELEASED,
            DETENTION_DATE::TEXT AS DETENTION_DATE,
            DETENTION_LOCATION::TEXT AS DETENTION_LOCATION,
            DETENTION_FACILITY_TYPE::TEXT AS DETENTION_FACILITY_TYPE
        FROM rel.A_TblCase
        WHERE IDNCASE IS NOT NULL
    """)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE _new_proceedings AS
        SELECT
            p.IDNPROCEEDING::TEXT AS IDNPROCEEDING,
            p.IDNCASE::TEXT AS IDNCASE,
            p.IJ_CODE::TEXT AS IJ_CODE,
            COALESCE(j.JUDGE_NAME, p.IJ_CODE)::TEXT AS JUDGE_NAME,
            p.HEARING_LOC_CODE::TEXT AS COURT,
            COALESCE(c.COURT_CITY, p.HEARING_LOC_CODE)::TEXT AS COURT_CITY,
            c.COURT_STATE::TEXT AS COURT_STATE,
            c.CIRCUIT::TEXT AS CIRCUIT,
            p.CASE_TYPE::TEXT AS PROCEEDING_TYPE,
            p.OSC_DATE::TEXT AS OSC_DATE,
            p.INPUT_DATE::TEXT AS INPUT_DATE,
            p.HEARING_DATE::TEXT AS HEARING_DATE,
            p.DEC_CODE::TEXT AS OUTCOME,
            d.OUTCOME_DESCRIPTION::TEXT AS OUTCOME_DESCRIPTION,
            p.COMP_DATE::TEXT AS DECISION_DATE,
            CASE
                WHEN NULLIF(p.APPEAL_RSVD, '') IS NOT NULL OR NULLIF(p.APPEAL_NOT_FILED, '') IS NOT NULL
                THEN COALESCE(NULLIF(p.APPEAL_RSVD, ''), NULLIF(p.APPEAL_NOT_FILED, ''))
                ELSE NULL
            END::TEXT AS APPEAL_FILED,
            p.ABSENTIA::TEXT AS ABSENTIA,
            p.CUSTODY::TEXT AS CUSTODY,
            p.NAT::TEXT AS NAT,
            p.LANG::TEXT AS LANG,
            p.DATE_DETAINED::TEXT AS DATE_DETAINED,
            p.DATE_RELEASED::TEXT AS DATE_RELEASED
        FROM rel.B_TblProceeding p
        LEFT JOIN _court_lookup c ON c.COURT = p.HEARING_LOC_CODE
        LEFT JOIN _judge_lookup j ON j.IJ_CODE = p.IJ_CODE
        LEFT JOIN _decision_lookup d ON d.CASE_TYPE = p.CASE_TYPE AND d.OUTCOME = p.DEC_CODE
        WHERE p.IDNPROCEEDING IS NOT NULL
    """)

    con.execute("""
        CREATE OR REPLACE TEMP TABLE _new_applications AS
        SELECT
            IDNPROCEEDINGAPPLN::TEXT AS IDNAPPLICATION,
            IDNPROCEEDING::TEXT AS IDNPROCEEDING,
            IDNCASE::TEXT AS IDNCASE,
            APPL_CODE::TEXT AS APPLICATION_TYPE,
            APPL_RECD_DATE::TEXT AS FILED_DATE,
            NULL::TEXT AS DECISION_DATE,
            APPL_DEC::TEXT AS DECISION
        FROM rel.E_TblApplication
        WHERE IDNPROCEEDINGAPPLN IS NOT NULL
    """)

    if "tblLookupNationality" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_nationalities AS
            SELECT
                NAT_CODE::TEXT AS NAT_CODE,
                NAT_NAME::TEXT AS NAT_NAME,
                NAT_COUNTRY_NAME::TEXT AS NAT_COUNTRY_NAME
            FROM rel.tblLookupNationality
            WHERE NAT_CODE IS NOT NULL
            QUALIFY row_number() OVER (
                PARTITION BY NAT_CODE
                ORDER BY blnActive DESC NULLS LAST
            ) = 1
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_nationalities (
                NAT_CODE TEXT, NAT_NAME TEXT, NAT_COUNTRY_NAME TEXT
            )
        """)

    if False and "D_TblAssociatedBond" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_bonds AS
            SELECT
                IDNASSOCBOND::TEXT AS IDNBOND,
                IDNPROCEEDING::TEXT AS IDNPROCEEDING,
                IDNCASE::TEXT AS IDNCASE,
                IJ_CODE::TEXT AS IJ_CODE,
                HEARING_LOC_CODE::TEXT AS COURT,
                BASE_CITY_NAME::TEXT AS COURT_CITY,
                DEC::TEXT AS DECISION,
                COMP_DATE::TEXT AS DECISION_DATE,
                TRY_CAST(INITIAL_BOND AS DOUBLE) AS INITIAL_BOND,
                TRY_CAST(NEW_BOND AS DOUBLE) AS NEW_BOND,
                BOND_TYPE::TEXT AS BOND_TYPE,
                BOND_HEAR_REQ_DATE::TEXT AS REQUEST_DATE
        FROM rel.D_TblAssociatedBond
        WHERE IDNASSOCBOND IS NOT NULL
    """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_bonds (
                IDNBOND TEXT, IDNPROCEEDING TEXT, IDNCASE TEXT, IJ_CODE TEXT,
                COURT TEXT, COURT_CITY TEXT, DECISION TEXT, DECISION_DATE TEXT,
                INITIAL_BOND DOUBLE, NEW_BOND DOUBLE, BOND_TYPE TEXT, REQUEST_DATE TEXT
            )
        """)

    if False and "tbl_CustodyHistory" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_custody AS
            SELECT
                IDNCUSTODY::TEXT AS IDNCUSTODY,
                IDNCASE::TEXT AS IDNCASE,
                CUSTODY::TEXT AS CUSTODY,
                DATDETAINED::TEXT AS DATDETAINED,
                DATRELEASED::TEXT AS DATRELEASED
        FROM rel.tbl_CustodyHistory
        WHERE IDNCUSTODY IS NOT NULL
    """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_custody (
                IDNCUSTODY TEXT, IDNCASE TEXT, CUSTODY TEXT, DATDETAINED TEXT, DATRELEASED TEXT
            )
        """)

    if False and "tbl_JuvenileHistory" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_juveniles AS
            SELECT
                idnJuvenileHistory::TEXT AS IDNJUVENILEHISTORY,
                idnCase::TEXT AS IDNCASE,
                idnProceeding::TEXT AS IDNPROCEEDING,
                idnJuvenile::TEXT AS IDNJUVENILE,
                DATCREATEDON::TEXT AS CREATED_ON,
                DATMODIFIEDON::TEXT AS MODIFIED_ON
        FROM rel.tbl_JuvenileHistory
        WHERE idnJuvenileHistory IS NOT NULL
    """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_juveniles (
                IDNJUVENILEHISTORY TEXT, IDNCASE TEXT, IDNPROCEEDING TEXT,
                IDNJUVENILE TEXT, CREATED_ON TEXT, MODIFIED_ON TEXT
            )
        """)

    if False and "tblAppeal" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_appeals AS
            SELECT
                idnAppeal::TEXT AS IDNAPPEAL,
                idncase::TEXT AS IDNCASE,
                idnProceeding::TEXT AS IDNPROCEEDING,
                strAppealCategory::TEXT AS APPEAL_CATEGORY,
                strAppealType::TEXT AS APPEAL_TYPE,
                datAppealFiled::TEXT AS FILED_DATE,
                strFiledBy::TEXT AS FILED_BY,
                datBIADecision::TEXT AS BIA_DECISION_DATE,
                strBIADecision::TEXT AS BIA_DECISION,
                strBIADecisionType::TEXT AS BIA_DECISION_TYPE,
                strCaseType::TEXT AS CASE_TYPE,
                strNat::TEXT AS NAT,
                strCustody::TEXT AS CUSTODY
        FROM rel.tblAppeal
        WHERE idnAppeal IS NOT NULL
    """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_appeals (
                IDNAPPEAL TEXT, IDNCASE TEXT, IDNPROCEEDING TEXT, APPEAL_CATEGORY TEXT,
                APPEAL_TYPE TEXT, FILED_DATE TEXT, FILED_BY TEXT, BIA_DECISION_DATE TEXT,
                BIA_DECISION TEXT, BIA_DECISION_TYPE TEXT, CASE_TYPE TEXT, NAT TEXT, CUSTODY TEXT
            )
        """)

    if False and "tblAppealFedCourts" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_fed_appeals AS
            SELECT
                idnAppealFedCourts::TEXT AS IDNFEDAPPEAL,
                lngAppealID::TEXT AS IDNAPPEAL,
                datRequestedByOIL::TEXT AS REQUESTED_BY_OIL_DATE,
                NULL::TEXT AS FED_DECISION_DATE,
                strFedCourtDecision::TEXT AS FED_DECISION
            FROM rel.tblAppealFedCourts
            WHERE idnAppealFedCourts IS NOT NULL
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_fed_appeals (
                IDNFEDAPPEAL TEXT, IDNAPPEAL TEXT, REQUESTED_BY_OIL_DATE TEXT,
                FED_DECISION_DATE TEXT, FED_DECISION TEXT
            )
        """)

    if False and "tblThreeMbrReferrals" in rel_tables:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_three_member_referrals AS
            SELECT
                idn3MemberReferral::TEXT AS IDNREFERRAL,
                lngAppealID::TEXT AS IDNAPPEAL,
                datReferredTo3Member::TEXT AS REFERRED_DATE,
                datRemovedFromReferral::TEXT AS REMOVED_DATE
            FROM rel.tblThreeMbrReferrals
            WHERE idn3MemberReferral IS NOT NULL
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TEMP TABLE _new_three_member_referrals (
                IDNREFERRAL TEXT, IDNAPPEAL TEXT, REFERRED_DATE TEXT, REMOVED_DATE TEXT
            )
        """)


def _merge_table(
    con: duckdb.DuckDBPyConnection,
    target: str,
    staged: str,
    pk: str,
    data_cols: list[str],
    release_tag: str,
) -> int:
    all_insert_cols = [pk, *data_cols, "_first_seen_release", "_last_seen_release"]
    select_cols = [pk, *data_cols, f"'{release_tag}'", f"'{release_tag}'"]

    target_count = con.execute(f"SELECT COUNT(*) FROM {qident(target)}").fetchone()[0]
    if target_count == 0:
        con.execute(f"""
            INSERT INTO {qident(target)}
                ({', '.join(qident(c) for c in all_insert_cols)})
            SELECT {', '.join(select_cols)}
            FROM (
                SELECT *,
                       row_number() OVER (PARTITION BY {qident(pk)} ORDER BY {qident(pk)}) AS _pk_rank
                FROM {qident(staged)}
                WHERE NULLIF(TRIM(REPLACE({qident(pk)}, chr(0), '')), '') IS NOT NULL
            ) AS s
            WHERE _pk_rank = 1
        """)
        return 0

    con.execute(f"""
        INSERT OR IGNORE INTO {qident(target)}
            ({', '.join(qident(c) for c in all_insert_cols)})
        SELECT {', '.join(select_cols)}
        FROM {qident(staged)}
    """)

    assignments = ",\n                ".join(
        [f"{qident(col)} = s.{qident(col)}" for col in data_cols]
        + [
            f"_last_seen_release = '{release_tag}'",
            "_current = TRUE",
        ]
    )
    con.execute(f"""
        UPDATE {qident(target)} AS t
        SET {assignments}
        FROM {qident(staged)} AS s
        WHERE t.{qident(pk)} = s.{qident(pk)}
    """)

    deletions = con.execute(f"""
        SELECT COUNT(*) FROM {qident(target)}
        WHERE _current = TRUE
          AND _last_seen_release != '{release_tag}'
    """).fetchone()[0]

    if deletions:
        con.execute(f"""
            UPDATE {qident(target)}
            SET _current = FALSE,
                _ever_deleted = TRUE,
                _deletion_releases = COALESCE(_deletion_releases || ',', '') || '{release_tag}'
            WHERE _current = TRUE
              AND _last_seen_release != '{release_tag}'
        """)
    return deletions


def upsert_release(
    con: duckdb.DuckDBPyConnection,
    release_tag: str,
    ingest_db: Path | None = None,
) -> dict:
    _attach_release(con, release_tag, ingest_db=ingest_db)
    _stage_release(con)

    stats = {"release_tag": release_tag, "deletions_flagged": 0}

    stats["deletions_flagged"] += _merge_table(
        con,
        "canonical_cases",
        "_new_cases",
        "IDNCASE",
        [
            "ANUMBER", "NAT", "LANG", "GENDER", "INPUT_DATE", "COMP_DATE",
            "NTA_DATE", "CUSTDY", "ATTY_NBR", "CASE_TYPE", "LATEST_HEARING",
            "DATE_DETAINED", "DATE_RELEASED", "DETENTION_DATE",
            "DETENTION_LOCATION", "DETENTION_FACILITY_TYPE",
        ],
        release_tag,
    )

    stats["deletions_flagged"] += _merge_table(
        con,
        "canonical_proceedings",
        "_new_proceedings",
        "IDNPROCEEDING",
        [
            "IDNCASE", "IJ_CODE", "JUDGE_NAME", "COURT", "COURT_CITY",
            "COURT_STATE", "CIRCUIT", "PROCEEDING_TYPE",
            "OSC_DATE", "INPUT_DATE", "HEARING_DATE", "OUTCOME",
            "OUTCOME_DESCRIPTION", "DECISION_DATE", "APPEAL_FILED",
            "ABSENTIA", "CUSTODY", "NAT", "LANG", "DATE_DETAINED", "DATE_RELEASED",
        ],
        release_tag,
    )

    stats["deletions_flagged"] += _merge_table(
        con,
        "canonical_applications",
        "_new_applications",
        "IDNAPPLICATION",
        [
            "IDNPROCEEDING", "IDNCASE", "APPLICATION_TYPE", "FILED_DATE",
            "DECISION_DATE", "DECISION",
        ],
        release_tag,
    )

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_nationalities
            (NAT_CODE, NAT_NAME, NAT_COUNTRY_NAME, _last_seen_release)
        SELECT NAT_CODE, NAT_NAME, NAT_COUNTRY_NAME, '{release_tag}'
        FROM _new_nationalities
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_bonds
            (IDNBOND, IDNPROCEEDING, IDNCASE, IJ_CODE, COURT, COURT_CITY,
             DECISION, DECISION_DATE, INITIAL_BOND, NEW_BOND, BOND_TYPE,
             REQUEST_DATE, _last_seen_release)
        SELECT IDNBOND, IDNPROCEEDING, IDNCASE, IJ_CODE, COURT, COURT_CITY,
               DECISION, DECISION_DATE, INITIAL_BOND, NEW_BOND, BOND_TYPE,
               REQUEST_DATE, '{release_tag}'
        FROM _new_bonds
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_custody_history
            (IDNCUSTODY, IDNCASE, CUSTODY, DATDETAINED, DATRELEASED, _last_seen_release)
        SELECT IDNCUSTODY, IDNCASE, CUSTODY, DATDETAINED, DATRELEASED, '{release_tag}'
        FROM _new_custody
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_juvenile_history
            (IDNJUVENILEHISTORY, IDNCASE, IDNPROCEEDING, IDNJUVENILE,
             CREATED_ON, MODIFIED_ON, _last_seen_release)
        SELECT IDNJUVENILEHISTORY, IDNCASE, IDNPROCEEDING, IDNJUVENILE,
               CREATED_ON, MODIFIED_ON, '{release_tag}'
        FROM _new_juveniles
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_appeals
            (IDNAPPEAL, IDNCASE, IDNPROCEEDING, APPEAL_CATEGORY, APPEAL_TYPE,
             FILED_DATE, FILED_BY, BIA_DECISION_DATE, BIA_DECISION,
             BIA_DECISION_TYPE, CASE_TYPE, NAT, CUSTODY, _last_seen_release)
        SELECT IDNAPPEAL, IDNCASE, IDNPROCEEDING, APPEAL_CATEGORY, APPEAL_TYPE,
               FILED_DATE, FILED_BY, BIA_DECISION_DATE, BIA_DECISION,
               BIA_DECISION_TYPE, CASE_TYPE, NAT, CUSTODY, '{release_tag}'
        FROM _new_appeals
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_fed_appeals
            (IDNFEDAPPEAL, IDNAPPEAL, REQUESTED_BY_OIL_DATE, FED_DECISION_DATE,
             FED_DECISION, _last_seen_release)
        SELECT IDNFEDAPPEAL, IDNAPPEAL, REQUESTED_BY_OIL_DATE, FED_DECISION_DATE,
               FED_DECISION, '{release_tag}'
        FROM _new_fed_appeals
    """)

    con.execute(f"""
        INSERT OR REPLACE INTO canonical_three_member_referrals
            (IDNREFERRAL, IDNAPPEAL, REFERRED_DATE, REMOVED_DATE, _last_seen_release)
        SELECT IDNREFERRAL, IDNAPPEAL, REFERRED_DATE, REMOVED_DATE, '{release_tag}'
        FROM _new_three_member_referrals
    """)

    rel_tables = {row[0] for row in con.execute("SHOW TABLES FROM rel").fetchall()}

    if "D_TblAssociatedBond" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_bonds
                (IDNBOND, IDNPROCEEDING, IDNCASE, IJ_CODE, COURT, COURT_CITY,
                 DECISION, DECISION_DATE, INITIAL_BOND, NEW_BOND, BOND_TYPE,
                 REQUEST_DATE, _last_seen_release)
            SELECT
                IDNASSOCBOND::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                IJ_CODE::TEXT,
                HEARING_LOC_CODE::TEXT,
                BASE_CITY_NAME::TEXT,
                DEC::TEXT,
                COMP_DATE::TEXT,
                TRY_CAST(INITIAL_BOND AS DOUBLE),
                TRY_CAST(NEW_BOND AS DOUBLE),
                BOND_TYPE::TEXT,
                BOND_HEAR_REQ_DATE::TEXT,
                '{release_tag}'
            FROM rel.D_TblAssociatedBond
            WHERE IDNASSOCBOND IS NOT NULL
        """)

    if "tbl_CustodyHistory" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_custody_history
                (IDNCUSTODY, IDNCASE, CUSTODY, DATDETAINED, DATRELEASED, _last_seen_release)
            SELECT
                IDNCUSTODY::TEXT,
                IDNCASE::TEXT,
                CUSTODY::TEXT,
                DATDETAINED::TEXT,
                DATRELEASED::TEXT,
                '{release_tag}'
            FROM rel.tbl_CustodyHistory
            WHERE IDNCUSTODY IS NOT NULL
        """)

    if "tbl_JuvenileHistory" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_juvenile_history
                (IDNJUVENILEHISTORY, IDNCASE, IDNPROCEEDING, IDNJUVENILE,
                 CREATED_ON, MODIFIED_ON, _last_seen_release)
            SELECT
                idnJuvenileHistory::TEXT,
                idnCase::TEXT,
                idnProceeding::TEXT,
                idnJuvenile::TEXT,
                DATCREATEDON::TEXT,
                DATMODIFIEDON::TEXT,
                '{release_tag}'
            FROM rel.tbl_JuvenileHistory
            WHERE idnJuvenileHistory IS NOT NULL
        """)

    if "tblAppeal" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_appeals
                (IDNAPPEAL, IDNCASE, IDNPROCEEDING, APPEAL_CATEGORY, APPEAL_TYPE,
                 FILED_DATE, FILED_BY, BIA_DECISION_DATE, BIA_DECISION,
                 BIA_DECISION_TYPE, CASE_TYPE, NAT, CUSTODY, _last_seen_release)
            SELECT
                idnAppeal::TEXT,
                idncase::TEXT,
                idnProceeding::TEXT,
                strAppealCategory::TEXT,
                strAppealType::TEXT,
                datAppealFiled::TEXT,
                strFiledBy::TEXT,
                datBIADecision::TEXT,
                strBIADecision::TEXT,
                strBIADecisionType::TEXT,
                strCaseType::TEXT,
                strNat::TEXT,
                strCustody::TEXT,
                '{release_tag}'
            FROM rel.tblAppeal
            WHERE idnAppeal IS NOT NULL
        """)

    if "tblAppealFedCourts" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_fed_appeals
                (IDNFEDAPPEAL, IDNAPPEAL, REQUESTED_BY_OIL_DATE, FED_DECISION_DATE,
                 FED_DECISION, _last_seen_release)
            SELECT
                idnAppealFedCourts::TEXT,
                lngAppealID::TEXT,
                datRequestedByOIL::TEXT,
                NULL::TEXT,
                strFedCourtDecision::TEXT,
                '{release_tag}'
            FROM rel.tblAppealFedCourts
            WHERE idnAppealFedCourts IS NOT NULL
        """)

    if "tblThreeMbrReferrals" in rel_tables:
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_three_member_referrals
                (IDNREFERRAL, IDNAPPEAL, REFERRED_DATE, REMOVED_DATE, _last_seen_release)
            SELECT
                idn3MemberReferral::TEXT,
                lngAppealID::TEXT,
                datReferredTo3Member::TEXT,
                datRemovedFromReferral::TEXT,
                '{release_tag}'
            FROM rel.tblThreeMbrReferrals
            WHERE idn3MemberReferral IS NOT NULL
        """)

    if "tbl_schedule" in rel_tables:
        con.execute(f"DELETE FROM canonical_schedules WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_schedules
                (IDNSCHEDULE, IDNPROCEEDING, IDNCASE, HEARING_LOC_CODE, BASE_CITY_CODE,
                 IJ_CODE, ADJ_DATE, ADJ_RSN, ADJ_MEDIUM, ADJ_ELAP_DAYS, SCHEDULE_TYPE,
                 CAL_TYPE, NOTICE_CODE, ATTORNEY_ID, _last_seen_release)
            SELECT
                IDNSCHEDULE::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                HEARING_LOC_CODE::TEXT,
                BASE_CITY_CODE::TEXT,
                IJ_CODE::TEXT,
                ADJ_DATE::TEXT,
                ADJ_RSN::TEXT,
                ADJ_MEDIUM::TEXT,
                ADJ_ELAP_DAYS::TEXT,
                SCHEDULE_TYPE::TEXT,
                CAL_TYPE::TEXT,
                NOTICE_CODE::TEXT,
                EOIRAttorneyID::TEXT,
                '{release_tag}'
            FROM rel.tbl_schedule
            WHERE IDNSCHEDULE IS NOT NULL
        """)

    if "B_TblProceedCharges" in rel_tables:
        con.execute(f"DELETE FROM canonical_charges WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_charges
                (IDNCHARGE, IDNPROCEEDING, IDNCASE, CHARGE, CHARGE_STATUS, _last_seen_release)
            SELECT
                IDNPRCDCHG::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                CHARGE::TEXT,
                CHG_STATUS::TEXT,
                '{release_tag}'
            FROM rel.B_TblProceedCharges
            WHERE IDNPRCDCHG IS NOT NULL
        """)

    if "tbl_RepsAssigned" in rel_tables:
        con.execute(f"DELETE FROM canonical_rep_assignments WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_rep_assignments
                (IDNREPASSIGNMENT, IDNCASE, ATTY_LEVEL, ATTY_TYPE, PARENT_TABLE,
                 PARENT_IDN, BASE_CITY_CODE, ASSIGNED_DATE, E27_DATE, E28_DATE,
                 PRIME_ATTORNEY, _last_seen_release)
            SELECT
                IDNREPSASSIGNED::TEXT,
                IDNCASE::TEXT,
                STRATTYLEVEL::TEXT,
                STRATTYTYPE::TEXT,
                PARENT_TABLE::TEXT,
                PARENT_IDN::TEXT,
                BASE_CITY_CODE::TEXT,
                INS_TA_DATE_ASSIGNED::TEXT,
                E_27_DATE::TEXT,
                E_28_DATE::TEXT,
                BLNPRIMEATTY::TEXT,
                '{release_tag}'
            FROM rel.tbl_RepsAssigned
            WHERE IDNREPSASSIGNED IS NOT NULL
        """)

    if "tbl_EOIR_Attorney" in rel_tables:
        con.execute(f"DELETE FROM canonical_attorneys WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_attorneys
                (ATTORNEY_ID, OLD_ATTORNEY_ID, BASE_CITY_CODE, ACTIVE, SOURCE_FLAG,
                 CREATED_ON, MODIFIED_ON, _last_seen_release)
            SELECT
                EOIRAttorneyID::TEXT,
                OldAttorneyID::TEXT,
                BaseCityCode::TEXT,
                blnAttorneyActive::TEXT,
                Source_Flag::TEXT,
                datCreatedOn::TEXT,
                datModifiedOn::TEXT,
                '{release_tag}'
            FROM rel.tbl_EOIR_Attorney
            WHERE EOIRAttorneyID IS NOT NULL
        """)

    if "tbl_Court_Motions" in rel_tables:
        con.execute(f"DELETE FROM canonical_motions WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_motions
                (IDNMOTION, IDNPROCEEDING, IDNCASE, HEARING_LOC_CODE, BASE_CITY_CODE,
                 IJ_CODE, MOTION_RECD_DATE, MOTION_DUE_DATE, RESP_DUE_DATE, DECISION,
                 COMP_DATE, FILING_PARTY, FILING_METHOD, STAY_GRANT, JURISDICTION,
                 _last_seen_release)
            SELECT
                IDNMOTION::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                HEARING_LOC_CODE::TEXT,
                BASE_CITY_CODE::TEXT,
                IJ_CODE::TEXT,
                MOTION_RECD_DATE::TEXT,
                DATMOTIONDUE::TEXT,
                RESP_DUE_DATE::TEXT,
                DEC::TEXT,
                COMP_DATE::TEXT,
                STRFILINGPARTY::TEXT,
                STRFILINGMETHOD::TEXT,
                STAY_GRANT::TEXT,
                JURISDICTION::TEXT,
                '{release_tag}'
            FROM rel.tbl_Court_Motions
            WHERE IDNMOTION IS NOT NULL
        """)

    stats["case_count"] = con.execute("SELECT COUNT(*) FROM canonical_cases").fetchone()[0]
    stats["proceeding_count"] = con.execute("SELECT COUNT(*) FROM canonical_proceedings").fetchone()[0]
    stats["application_count"] = con.execute("SELECT COUNT(*) FROM canonical_applications").fetchone()[0]

    con.execute(f"""
        INSERT OR REPLACE INTO _release_log
            (release_tag, ingested_at, case_count, proceeding_count, application_count, deletions_flagged)
        VALUES
            ('{release_tag}', current_timestamp, {stats['case_count']},
             {stats['proceeding_count']}, {stats['application_count']},
             {stats['deletions_flagged']})
    """)
    con.execute("CHECKPOINT")
    log.info(
        "Canonical upsert complete: %d cases, %d proceedings, %d applications",
        stats["case_count"],
        stats["proceeding_count"],
        stats["application_count"],
    )
    return stats


def load_extended_only(
    con: duckdb.DuckDBPyConnection,
    release_tag: str,
    ingest_db: Path | None = None,
) -> dict:
    """Load optional high-volume roadmap tables without re-merging core tables."""
    _attach_release(con, release_tag, ingest_db=ingest_db)
    rel_tables = {row[0] for row in con.execute("SHOW TABLES FROM rel").fetchall()}
    stats = {"release_tag": release_tag}

    if "tbl_schedule" in rel_tables:
        con.execute(f"DELETE FROM canonical_schedules WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_schedules
                (IDNSCHEDULE, IDNPROCEEDING, IDNCASE, HEARING_LOC_CODE, BASE_CITY_CODE,
                 IJ_CODE, ADJ_DATE, ADJ_RSN, ADJ_MEDIUM, ADJ_ELAP_DAYS, SCHEDULE_TYPE,
                 CAL_TYPE, NOTICE_CODE, ATTORNEY_ID, _last_seen_release)
            SELECT
                IDNSCHEDULE::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                HEARING_LOC_CODE::TEXT,
                BASE_CITY_CODE::TEXT,
                IJ_CODE::TEXT,
                ADJ_DATE::TEXT,
                ADJ_RSN::TEXT,
                ADJ_MEDIUM::TEXT,
                ADJ_ELAP_DAYS::TEXT,
                SCHEDULE_TYPE::TEXT,
                CAL_TYPE::TEXT,
                NOTICE_CODE::TEXT,
                EOIRAttorneyID::TEXT,
                '{release_tag}'
            FROM rel.tbl_schedule
            WHERE IDNSCHEDULE IS NOT NULL
        """)
        stats["schedule_count"] = con.execute("SELECT COUNT(*) FROM canonical_schedules").fetchone()[0]

    if "B_TblProceedCharges" in rel_tables:
        con.execute(f"DELETE FROM canonical_charges WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_charges
                (IDNCHARGE, IDNPROCEEDING, IDNCASE, CHARGE, CHARGE_STATUS, _last_seen_release)
            SELECT
                IDNPRCDCHG::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                CHARGE::TEXT,
                CHG_STATUS::TEXT,
                '{release_tag}'
            FROM rel.B_TblProceedCharges
            WHERE IDNPRCDCHG IS NOT NULL
        """)
        stats["charge_count"] = con.execute("SELECT COUNT(*) FROM canonical_charges").fetchone()[0]

    if "tbl_RepsAssigned" in rel_tables:
        con.execute(f"DELETE FROM canonical_rep_assignments WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_rep_assignments
                (IDNREPASSIGNMENT, IDNCASE, ATTY_LEVEL, ATTY_TYPE, PARENT_TABLE,
                 PARENT_IDN, BASE_CITY_CODE, ASSIGNED_DATE, E27_DATE, E28_DATE,
                 PRIME_ATTORNEY, _last_seen_release)
            SELECT
                IDNREPSASSIGNED::TEXT,
                IDNCASE::TEXT,
                STRATTYLEVEL::TEXT,
                STRATTYTYPE::TEXT,
                PARENT_TABLE::TEXT,
                PARENT_IDN::TEXT,
                BASE_CITY_CODE::TEXT,
                INS_TA_DATE_ASSIGNED::TEXT,
                E_27_DATE::TEXT,
                E_28_DATE::TEXT,
                BLNPRIMEATTY::TEXT,
                '{release_tag}'
            FROM rel.tbl_RepsAssigned
            WHERE IDNREPSASSIGNED IS NOT NULL
        """)
        stats["rep_assignment_count"] = con.execute("SELECT COUNT(*) FROM canonical_rep_assignments").fetchone()[0]

    if "tbl_EOIR_Attorney" in rel_tables:
        con.execute(f"DELETE FROM canonical_attorneys WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT OR REPLACE INTO canonical_attorneys
                (ATTORNEY_ID, OLD_ATTORNEY_ID, BASE_CITY_CODE, ACTIVE, SOURCE_FLAG,
                 CREATED_ON, MODIFIED_ON, _last_seen_release)
            SELECT
                EOIRAttorneyID::TEXT,
                OldAttorneyID::TEXT,
                BaseCityCode::TEXT,
                blnAttorneyActive::TEXT,
                Source_Flag::TEXT,
                datCreatedOn::TEXT,
                datModifiedOn::TEXT,
                '{release_tag}'
            FROM rel.tbl_EOIR_Attorney
            WHERE EOIRAttorneyID IS NOT NULL
        """)
        stats["attorney_count"] = con.execute("SELECT COUNT(*) FROM canonical_attorneys").fetchone()[0]

    if "tbl_Court_Motions" in rel_tables:
        con.execute(f"DELETE FROM canonical_motions WHERE _last_seen_release = '{release_tag}'")
        con.execute(f"""
            INSERT INTO canonical_motions
                (IDNMOTION, IDNPROCEEDING, IDNCASE, HEARING_LOC_CODE, BASE_CITY_CODE,
                 IJ_CODE, MOTION_RECD_DATE, MOTION_DUE_DATE, RESP_DUE_DATE, DECISION,
                 COMP_DATE, FILING_PARTY, FILING_METHOD, STAY_GRANT, JURISDICTION,
                 _last_seen_release)
            SELECT
                IDNMOTION::TEXT,
                IDNPROCEEDING::TEXT,
                IDNCASE::TEXT,
                HEARING_LOC_CODE::TEXT,
                BASE_CITY_CODE::TEXT,
                IJ_CODE::TEXT,
                MOTION_RECD_DATE::TEXT,
                DATMOTIONDUE::TEXT,
                RESP_DUE_DATE::TEXT,
                DEC::TEXT,
                COMP_DATE::TEXT,
                STRFILINGPARTY::TEXT,
                STRFILINGMETHOD::TEXT,
                STAY_GRANT::TEXT,
                JURISDICTION::TEXT,
                '{release_tag}'
            FROM rel.tbl_Court_Motions
            WHERE IDNMOTION IS NOT NULL
        """)
        stats["motion_count"] = con.execute("SELECT COUNT(*) FROM canonical_motions").fetchone()[0]

    con.execute("CHECKPOINT")
    log.info("Extended canonical load complete: %s", stats)
    return stats


if __name__ == "__main__":
    from scripts.ingest import list_bronze_releases

    parser = argparse.ArgumentParser(description="Upsert an ingested EOIR release into canonical Silver")
    releases = list_bronze_releases()
    parser.add_argument(
        "--release",
        default=releases[-1] if releases else None,
        help="Release tag (YYYY-MM). Defaults to latest.",
    )
    parser.add_argument(
        "--ingest-db",
        default=None,
        help="Optional ingested DuckDB path. Defaults to silver/<release>.duckdb.",
    )
    parser.add_argument(
        "--canonical-db",
        default=None,
        help="Optional canonical DuckDB output path. Defaults to silver/canonical.duckdb.",
    )
    parser.add_argument(
        "--extended-only",
        action="store_true",
        help="Load optional roadmap side tables without re-merging core case/proceeding/application tables.",
    )
    args = parser.parse_args()

    if not args.release:
        print("No bronze releases found. Run scripts/download.py first.")
        sys.exit(1)

    canonical_db = Path(args.canonical_db) if args.canonical_db else None
    con = get_canonical_con(canonical_db)
    init_canonical(con)
    ingest_db = Path(args.ingest_db) if args.ingest_db else None
    if args.extended_only:
        stats = load_extended_only(con, args.release, ingest_db=ingest_db)
    else:
        stats = upsert_release(con, args.release, ingest_db=ingest_db)
    con.close()
    print(f"Done: {stats}")
