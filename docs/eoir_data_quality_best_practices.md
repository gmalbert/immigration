# EOIR Immigration Court Data: Quality Best Practices
### Handling, validating, archiving, and publishing the EOIR CASE dataset responsibly
*Prepared June 2026*

---

## Overview

The EOIR CASE database is extraordinary in scope but documented in its quality problems. This guide covers every known issue, the best practices to handle each one, and the code and external resources that implement those practices. The goal is a pipeline that is reproducible, diff-tracked, and honest with the public about its limitations — which is how TRAC at Syracuse has maintained credibility for over 15 years on this data.

---

## Part 1: Understanding the Quality Problem Landscape

Before writing a single line of code, you need to know what you're dealing with. EOIR data has four distinct categories of quality risk:

### 1.1 Disappearing Records (The Most Serious Issue)

Between 2019 and 2022, TRAC documented EOIR systematically releasing monthly data extracts where records present in previous months were simply absent. Key documented instances:

- **October 2019:** Over 1,500 relief applications present in August's release were missing from September's release. Simultaneously, fields appeared mismatched to wrong variables — data was "garbled."
- **2020 peak:** TRAC estimated upwards of 60,000 asylum application records disappearing per month — more than the total number filed in an average month.
- **2019–2022 cumulative:** Over 17,706 asylum applications disappeared from EOIR files entirely.
- **Venue transfer bug:** Over 50,000 pending asylum applications were lost from tracking after a case changed venue. The original filing record was still in historical data, but the case "forgot" it had an asylum application filed.
- **Aggregate impact:** A year-over-year comparison in 2019 found nearly 897,000 records had been removed from EOIR's releases.

EOIR initially denied the problem. The Congressional Hispanic Caucus sent a formal letter to EOIR's Director. The GAO opened an investigation. EOIR eventually restored most records after public pressure, but TRAC documented "persistent problems" continuing at lower volumes.

**The implication for you:** Never treat the current month's release as the ground truth. Every release must be diffed against all prior releases. Records that disappear from a new release must be preserved in your canonical dataset and flagged, not deleted.

### 1.2 Structural Schema Changes Over Time

The database schema and code values have changed multiple times. Known breaking changes include:

- **Pre-1997 vs. Post-1997:** IIRIRA (1996) merged deportation and exclusion proceedings into unified "removal proceedings." Pre-April 1997 records use different proceedings terminology, different case type codes, and different charge structures. Any longitudinal analysis crossing this boundary requires harmonization.
- **May 2019:** EOIR deactivated the `"other"` outcome code for applications, replacing it with `"not adjudicated"`. Code that uses the old value will silently undercount outcomes in post-2019 data.
- **Administration-driven coding changes:** "Administrative closure" was coded consistently for years, then usage spiked dramatically under Obama (2011–2016), was nearly eliminated under Trump (2017–2020), and reopened under Biden. The code itself didn't change, but the policy behind what gets coded that way changed dramatically — creating the appearance of a statistical cliff in the raw data.
- **Code key updates:** EOIR periodically adds new court locations, nationality codes, and adjournment reason codes without publishing release notes. New codes appear as nulls or unknowns until you update your lookup tables.

### 1.3 Extraction and File Format Problems

The raw EOIR FOIA zip file has known practical issues:

- **ZIP extraction failure:** The Deportation Data Project explicitly notes: "The ZIP file provided by EOIR does not extract properly with some standard archive utilities." Use Python's `zipfile` module or the `7zip` command-line tool rather than OS-level double-click extraction.
- **Pipe-delimited, not comma-delimited:** Files use `|` as the delimiter, not `,`. Tools that assume CSV will silently misparse.
- **Encoding inconsistency:** Files have historically used Windows-1252 (CP1252) encoding rather than UTF-8, causing failures on non-Windows systems when loading nationality names and other fields with international characters.
- **30+ GB uncompressed:** The full release is 18 large pipe-delimited files totaling over 30GB uncompressed. Standard tools (Excel, naive pandas) will OOM or time out.
- **No release notes:** EOIR does not publish a changelog. There is no official notification when a new release is posted or what changed.

### 1.4 Scope Limitations (Structural, Not Bugs)

These are not errors — they are inherent limits you must disclose to users:

- **Expedited removal is excluded:** Cases where DHS/ICE removes someone without an immigration court hearing are not in EOIR data. This is an increasingly large share of total removals.
- **USCIS affirmative asylum excluded:** Only defensive asylum claims before immigration judges are here. Affirmative asylum (filed directly with USCIS) is a separate system.
- **Paper cases not fully digitized:** EOIR estimated approximately 1 million cases exist only in paper format. These appear partially or not at all in the digital data.
- **ICE dataset is separate and not matchable:** ICE tracks arrests, detentions, and deportations. EOIR tracks court proceedings. These overlap but cannot be matched at the individual level.
- **BIA opinions are not text:** The BIA issues written opinions, but the full text is not in the CASE database. You get outcome codes, not the legal reasoning.

---

## Part 2: Pipeline Architecture

### 2.1 The Medallion Architecture for EOIR Data

The recommended architecture follows the **Bronze / Silver / Gold** (Medallion) pattern:

```
Bronze: Raw monthly downloads, archived by date, never modified
   ↓
Silver: Cleaned, validated, harmonized, with diff-tracking applied
   ↓
Gold: Derived metrics, aggregated tables, materialized views for the site
```

This maps directly to the EOIR quality problems:
- **Bronze** protects against disappearing records (you always have the original)
- **Silver** applies all quality fixes transparently
- **Gold** serves the analytics layer

### 2.2 Directory Structure

```
eoir-pipeline/
├── bronze/
│   ├── 2024-01/          # Each monthly release in its own dated folder
│   │   ├── raw.zip       # Original file from EOIR, untouched
│   │   ├── checksum.sha256
│   │   ├── metadata.txt
│   │   ├── A_TblCase.txt
│   │   ├── B_TblProceeding.txt
│   │   └── ...
│   ├── 2024-02/
│   └── ...
├── silver/
│   ├── canonical.duckdb            # Never deletes — only appends/updates with provenance
│   └── diff_log/
│       ├── 2024-02_A_TblCase_deletions.csv
│       ├── 2024-02_E_TblApplication_deletions.csv
│       └── 2024-02_summary.csv
├── gold/
│   ├── judge_metrics.parquet
│   ├── court_metrics.parquet
│   └── nationality_metrics.parquet
├── scripts/
│   ├── download.py
│   ├── ingest.py
│   ├── diff.py
│   ├── canonical.py
│   ├── clean.py
│   └── aggregate.py
└── logs/
    └── pipeline_YYYY-MM.log
```

---

## Part 3: Ingestion Code

### 3.1 Download and Archive

```python
# scripts/download.py
"""
Downloads the latest EOIR FOIA release and archives it by date.
EOIR does not publish a release calendar; poll monthly and detect new releases
by checking the FOIA library page for new zip links.
"""

import os
import hashlib
import requests
import zipfile
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

EOIR_FOIA_URL = "https://www.justice.gov/eoir/foia-library-0"


def get_current_release_url(foia_page_url: str) -> str:
    """Scrape the EOIR FOIA library page and return the data download URL."""
    resp = requests.get(foia_page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".zip") and "eoir" in href.lower():
            return href

    raise ValueError("Could not locate EOIR case data download link on FOIA page")


def download_release(url: str, dest_dir: Path) -> Path:
    """Stream-download a large file to dest_dir. Returns path to saved file."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "raw.zip"

    if dest_path.exists():
        print(f"Already downloaded: {dest_path}")
        return dest_path

    print(f"Downloading {url} → {dest_path}")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)

    sha256 = hashlib.sha256(dest_path.read_bytes()).hexdigest()
    (dest_dir / "checksum.sha256").write_text(sha256)
    print(f"Download complete. SHA256: {sha256}")
    return dest_path


def extract_release(zip_path: Path, dest_dir: Path) -> None:
    """
    Extract the EOIR zip file.

    IMPORTANT: EOIR's zip does not extract with some standard OS tools.
    Python's zipfile module handles it reliably. If that fails, fall back to
    the 7zip CLI: `7z x file.zip -o/dest/dir`
    """
    print(f"Extracting {zip_path} → {dest_dir}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"Corrupt file in ZIP: {bad}")
            zf.extractall(dest_dir)
    except zipfile.BadZipFile as e:
        raise RuntimeError(
            f"EOIR zip extraction failed with Python zipfile: {e}\n"
            f"Fallback: run `7z x {zip_path} -o{dest_dir}`"
        )


def archive_release() -> Path:
    release_date = datetime.now().strftime("%Y-%m")
    bronze_dir = Path("bronze") / release_date

    if (bronze_dir / "A_TblCase.txt").exists():
        print(f"Release for {release_date} already archived.")
        return bronze_dir

    url = get_current_release_url(EOIR_FOIA_URL)
    (bronze_dir / "metadata.txt").parent.mkdir(parents=True, exist_ok=True)
    (bronze_dir / "metadata.txt").write_text(
        f"source_url: {url}\ndownloaded: {datetime.now().isoformat()}\n"
    )

    zip_path = download_release(url, bronze_dir)
    extract_release(zip_path, bronze_dir)
    print(f"Archived to: {bronze_dir}")
    return bronze_dir
```

### 3.2 Loading Pipe-Delimited Files

```python
# scripts/ingest.py
"""
Load EOIR pipe-delimited files into DuckDB.
Handles the known encoding and size issues.
"""

import pandas as pd
import duckdb
from pathlib import Path

# EOIR uses Windows-1252, not UTF-8. Nationality names will fail on latin-1
# systems without this. Fall back to latin-1 if windows-1252 still fails.
EOIR_ENCODING = "windows-1252"

EOIR_TABLES = {
    "A_TblCase":           "IDNCASE",
    "B_TblProceeding":     "IDNPROCEEDING",
    "C_TblSchedule":       "IDNSCHEDULE",
    "D_TblCharge":         "IDNCHARGE",
    "E_TblApplication":    "IDNAPPLICATION",
    "F_TblMotion":         "IDNMOTION",
    "G_TblRepresentative": "IDNREPRESENTATIVE",
    "H_TblCustodyHistory": "IDNCUSTODY",
    "I_TblBond":           "IDNBOND",
    "J_TblJuvenile":       "IDNJUVENILE",
    "K_TblLeadRider":      "IDNLEAD",
}


def load_table(release_dir: Path, table_name: str, con: duckdb.DuckDBPyConnection) -> int:
    """Load a single EOIR table. Returns row count."""
    file_path = release_dir / f"{table_name}.txt"
    if not file_path.exists():
        print(f"  WARNING: {table_name}.txt not found in {release_dir}")
        return 0

    try:
        df = pd.read_csv(
            file_path,
            sep="|",
            encoding=EOIR_ENCODING,
            low_memory=False,
            dtype=str,             # Load everything as strings; type-cast in silver layer
            on_bad_lines="warn",
        )
    except UnicodeDecodeError:
        print(f"  WARNING: windows-1252 failed for {table_name}, retrying with latin-1")
        df = pd.read_csv(
            file_path,
            sep="|",
            encoding="latin-1",
            low_memory=False,
            dtype=str,
            on_bad_lines="warn",
        )

    # Strip whitespace — EOIR pads many fields
    df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)
    df.columns = df.columns.str.upper()  # Normalize column names

    con.register(f"df_{table_name}", df)
    con.execute(
        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df_{table_name}"
    )

    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"  Loaded {table_name}: {row_count:,} rows")
    return row_count


def load_release(release_dir: Path, db_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    print(f"\nLoading {release_dir} → {db_path}")
    totals = {t: load_table(release_dir, t, con) for t in EOIR_TABLES}

    # Persist row counts for audit
    values = ", ".join(f"('{t}', {c})" for t, c in totals.items())
    con.execute(f"""
        CREATE OR REPLACE TABLE _ingest_audit AS
        SELECT * FROM (VALUES {values}) AS t(table_name, row_count)
    """)
    con.execute("CHECKPOINT")
    return con
```

---

## Part 4: The Diff Engine (Most Critical Component)

This is how TRAC detects disappearing records. Every month, compare the new release against the previous one. Records in Month N-1 that are absent from Month N are **deletions** — and given EOIR's documented history, some of these represent data quality failures, not legitimate corrections.

```python
# scripts/diff.py
"""
Compare two monthly EOIR releases and produce a full diff log.
"""

import pandas as pd
import duckdb
from pathlib import Path
from scripts.ingest import EOIR_TABLES, EOIR_ENCODING

# Thresholds above which deletion rates trigger a pipeline halt
DELETION_ALERT_THRESHOLDS = {
    "A_TblCase":        0.001,   # >0.1% case deletions = alert
    "E_TblApplication": 0.005,   # >0.5% application deletions = alert (historically most volatile)
    "B_TblProceeding":  0.001,
}


def diff_table(
    prev_dir: Path,
    curr_dir: Path,
    table_name: str,
    primary_key: str,
    diff_log_dir: Path,
) -> dict:
    """Diff a single table. Returns a summary dict."""
    prev_path = prev_dir / f"{table_name}.txt"
    curr_path = curr_dir / f"{table_name}.txt"

    if not prev_path.exists() or not curr_path.exists():
        return {"table": table_name, "error": "File missing in one or both releases"}

    def load(p):
        df = pd.read_csv(p, sep="|", encoding=EOIR_ENCODING,
                         low_memory=False, dtype=str, on_bad_lines="warn")
        df.columns = df.columns.str.upper()
        df = df.apply(lambda c: c.str.strip() if c.dtype == object else c)
        return df

    prev_df = load(prev_path)
    curr_df = load(curr_path)
    pk = primary_key.upper()

    if pk not in prev_df.columns:
        return {"table": table_name, "error": f"PK '{pk}' missing from prev release"}

    prev_ids = set(prev_df[pk].dropna())
    curr_ids = set(curr_df[pk].dropna())

    deleted_ids = prev_ids - curr_ids   # Records that disappeared
    added_ids   = curr_ids - prev_ids   # New records (expected monthly)
    common_ids  = prev_ids & curr_ids

    # Detect value changes on common records
    shared_cols = sorted(set(prev_df.columns) & set(curr_df.columns))
    prev_common = prev_df[prev_df[pk].isin(common_ids)].set_index(pk).sort_index()
    curr_common = curr_df[curr_df[pk].isin(common_ids)].set_index(pk).sort_index()
    changed_mask = (prev_common[shared_cols] != curr_common[shared_cols]).any(axis=1)
    changed_count = int(changed_mask.sum())

    summary = {
        "table":            table_name,
        "prev_count":       len(prev_ids),
        "curr_count":       len(curr_ids),
        "added":            len(added_ids),
        "deleted":          len(deleted_ids),
        "changed":          changed_count,
        "deletion_rate_pct": round(len(deleted_ids) / max(len(prev_ids), 1) * 100, 4),
    }

    # Save deletion log — these records must be preserved in canonical dataset
    if deleted_ids:
        deleted_df = prev_df[prev_df[pk].isin(deleted_ids)].copy()
        deleted_df["_deleted_from_release"] = curr_dir.name
        deleted_df["_last_present_release"] = prev_dir.name
        diff_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = diff_log_dir / f"{curr_dir.name}_{table_name}_deletions.csv"
        deleted_df.to_csv(log_path, index=False)
        print(f"  ⚠ {table_name}: {len(deleted_ids):,} DELETIONS → {log_path}")

    return summary


def diff_full_release(
    prev_dir: Path, curr_dir: Path, diff_log_dir: Path
) -> pd.DataFrame:
    """Diff all major tables. Returns summary DataFrame."""
    print(f"\nDiffing {prev_dir.name} → {curr_dir.name}")
    summaries = []
    for table_name, pk in EOIR_TABLES.items():
        result = diff_table(prev_dir, curr_dir, table_name, pk, diff_log_dir)
        summaries.append(result)
        if result.get("deletion_rate_pct", 0) > 1.0:
            print(f"  🚨 ALERT: {table_name} — {result['deletion_rate_pct']}% deletion rate")

    summary_df = pd.DataFrame(summaries)
    summary_path = diff_log_dir / f"{curr_dir.name}_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Diff summary → {summary_path}")
    return summary_df


def check_alerts(summary_df: pd.DataFrame) -> list:
    """Return alert strings for any anomalous deletion rates."""
    alerts = []
    for _, row in summary_df.iterrows():
        table = row.get("table")
        del_rate = row.get("deletion_rate_pct", 0) / 100
        threshold = DELETION_ALERT_THRESHOLDS.get(table, 0.01)
        if del_rate > threshold:
            alerts.append(
                f"⚠ {table}: {int(row['deleted']):,} records deleted "
                f"({row['deletion_rate_pct']}% of prior release). "
                f"Threshold: {threshold*100}%. Do not publish until investigated."
            )
    return alerts
```

---

## Part 5: The Canonical Dataset

The canonical dataset never deletes. It absorbs each release and preserves disappeared records with provenance metadata.

```python
# scripts/canonical.py
"""
Maintain the Silver-layer canonical dataset.
Every record ever seen in any EOIR release is kept.
Disappeared records are flagged, not deleted.
"""

import pandas as pd
import duckdb
from pathlib import Path

CANONICAL_DB = Path("silver/canonical.duckdb")


def init_canonical(con: duckdb.DuckDBPyConnection) -> None:
    """Create the canonical cases table if it doesn't exist."""
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
            -- Provenance fields (added by pipeline, not from EOIR)
            _first_seen_release    TEXT,
            _last_seen_release     TEXT,
            _ever_deleted          BOOLEAN DEFAULT FALSE,
            _deletion_releases     TEXT,
            _current               BOOLEAN DEFAULT TRUE
        )
    """)


def upsert_release(
    con: duckdb.DuckDBPyConnection, release_dir: Path, release_name: str
) -> None:
    """
    Merge a new monthly release into the canonical dataset.
    New records:     insert with provenance
    Existing records: update _last_seen_release
    Absent records:  mark _current=FALSE, flag _ever_deleted=TRUE
    """
    new_df = pd.read_csv(
        release_dir / "A_TblCase.txt",
        sep="|", encoding="windows-1252",
        low_memory=False, dtype=str, on_bad_lines="warn"
    )
    new_df.columns = new_df.columns.str.upper()
    new_df = new_df.apply(lambda c: c.str.strip() if c.dtype == object else c)
    con.register("new_release_df", new_df)

    # 1. Insert new records
    con.execute(f"""
        INSERT OR IGNORE INTO canonical_cases
            SELECT
                IDNCASE, ANUMBER, NAT, LANG, GENDER,
                INPUT_DATE, COMP_DATE, NTA_DATE, CUSTDY, ATTY_NBR,
                '{release_name}', '{release_name}',
                FALSE, NULL, TRUE
            FROM new_release_df
            WHERE IDNCASE NOT IN (SELECT IDNCASE FROM canonical_cases)
    """)

    # 2. Update records still present
    con.execute(f"""
        UPDATE canonical_cases
        SET _last_seen_release = '{release_name}', _current = TRUE
        WHERE IDNCASE IN (SELECT IDNCASE FROM new_release_df)
    """)

    # 3. Flag records no longer present
    con.execute(f"""
        UPDATE canonical_cases
        SET
            _current = FALSE,
            _ever_deleted = TRUE,
            _deletion_releases = COALESCE(_deletion_releases || ',', '') || '{release_name}'
        WHERE IDNCASE NOT IN (SELECT IDNCASE FROM new_release_df)
          AND _current = TRUE
    """)

    deleted_total = con.execute(
        "SELECT COUNT(*) FROM canonical_cases WHERE _ever_deleted = TRUE"
    ).fetchone()[0]
    print(f"Upsert complete for {release_name}. Ever-deleted records: {deleted_total:,}")
    con.execute("CHECKPOINT")
```

---

## Part 6: Cleaning and Harmonization

### 6.1 Type Casting and Derived Fields

```python
# scripts/clean.py
"""
Silver-layer transformations: types, derived fields, code normalization.
"""

import duckdb
import pandas as pd
from pathlib import Path


def clean_cases(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE silver_cases AS
        SELECT
            IDNCASE,
            ANUMBER,
            -- Parse EOIR's MM/DD/YYYY date strings
            TRY_CAST(STRPTIME(INPUT_DATE, '%m/%d/%Y') AS DATE) AS input_date,
            TRY_CAST(STRPTIME(COMP_DATE,  '%m/%d/%Y') AS DATE) AS comp_date,
            TRY_CAST(STRPTIME(NTA_DATE,   '%m/%d/%Y') AS DATE) AS nta_date,
            -- Derived: case age in days at completion
            CASE
                WHEN COMP_DATE IS NOT NULL AND NTA_DATE IS NOT NULL
                THEN DATEDIFF('day',
                    TRY_CAST(STRPTIME(NTA_DATE, '%m/%d/%Y') AS DATE),
                    TRY_CAST(STRPTIME(COMP_DATE, '%m/%d/%Y') AS DATE))
            END AS case_age_days,
            NAT   AS nationality_code,
            LANG  AS language_code,
            CUSTDY AS custody_code,
            -- Representation: blank attorney number = pro se
            CASE WHEN ATTY_NBR IS NULL OR TRIM(ATTY_NBR) = ''
                 THEN FALSE ELSE TRUE END AS is_represented,
            -- IIRIRA era flag — required for any longitudinal analysis
            CASE
                WHEN TRY_CAST(STRPTIME(NTA_DATE, '%m/%d/%Y') AS DATE) < '1997-04-01'
                THEN 'pre_iirira' ELSE 'post_iirira'
            END AS iirira_era,
            -- Provenance passthrough
            _first_seen_release,
            _last_seen_release,
            _ever_deleted,
            _current
        FROM canonical_cases
    """)


def normalize_application_outcomes(con: duckdb.DuckDBPyConnection) -> None:
    """
    CRITICAL: In May 2019, EOIR deactivated the 'other' application outcome code,
    replacing it with 'not_adjudicated'. Without normalization, any time-series
    analysis of outcomes crossing May 2019 will show an artificial cliff.
    Normalize both codes to 'not_adjudicated_normalized'.
    """
    con.execute("""
        CREATE OR REPLACE TABLE silver_applications AS
        SELECT
            *,
            CASE
                WHEN UPPER(APPL_DECISION_CODE) IN ('OTH', 'O')  -- pre-May 2019
                  OR UPPER(APPL_DECISION_CODE) IN ('NAD', 'N')  -- post-May 2019
                THEN 'not_adjudicated_normalized'
                ELSE APPL_DECISION_CODE
            END AS appl_decision_normalized
        FROM canonical_applications
    """)


def harmonize_pre_iirira_case_types(con: duckdb.DuckDBPyConnection) -> None:
    """
    Pre-April 1997: DEP (deportation) and EXC (exclusion) case types.
    Post-April 1997: RMV (removal) unified type.
    Normalize DEP and EXC to RMV for consistent longitudinal counts.
    Flag pre-IIRIRA cases; disclose this normalization in your UI.
    """
    con.execute("""
        CREATE OR REPLACE TABLE silver_proceedings AS
        SELECT
            *,
            CASE
                WHEN UPPER(CASE_TYPE) IN ('DEP', 'EXC') THEN 'RMV'
                ELSE CASE_TYPE
            END AS case_type_normalized,
            CASE WHEN INPUT_DATE < '1997-04-01'
                 THEN TRUE ELSE FALSE END AS is_pre_iirira
        FROM canonical_proceedings
    """)


def resolve_lookup_codes(con: duckdb.DuckDBPyConnection, code_key_path: Path) -> None:
    """
    Join all coded fields to human-readable names using the EOIR Code Key.
    The Code Key ships with each FOIA release (Excel or pipe-delimited).
    """
    nat_df = pd.read_excel(code_key_path, sheet_name="Nationality")
    nat_df.columns = ["nationality_code", "country_name"]
    nat_df["nationality_code"] = nat_df["nationality_code"].astype(str).str.strip()
    con.register("nationality_lookup", nat_df)

    con.execute("""
        CREATE OR REPLACE TABLE silver_cases AS
        SELECT
            c.*,
            COALESCE(n.country_name,
                'Unknown (' || c.nationality_code || ')') AS country_name
        FROM silver_cases c
        LEFT JOIN nationality_lookup n
            ON c.nationality_code = n.nationality_code
    """)
```

---

## Part 7: Key Metrics with Statistical Rigor

### 7.1 Asylum Grant Rate — TRAC Methodology

```python
def compute_asylum_grant_rate(con: duckdb.DuckDBPyConnection) -> None:
    """
    Grant rate = grants / (grants + denials)
    Excludes 'not_adjudicated_normalized', administrative closures, and abandonments
    from the denominator. This matches TRAC's published methodology and is more
    defensible than including all outcomes.

    EOIR's own published rates use a different denominator (all completions),
    producing lower rates. Your site should state which methodology you use.
    """
    con.execute("""
        CREATE OR REPLACE TABLE gold_asylum_rates AS
        SELECT
            p.IJ_CODE AS judge_id,
            c.country_name,
            YEAR(CAST(p.decision_date AS DATE)) AS decision_year,
            p.court_code,

            COUNT(*) FILTER (WHERE a.appl_decision_normalized = 'GRT') AS grants,
            COUNT(*) FILTER (WHERE a.appl_decision_normalized = 'DEN') AS denials,

            -- TRAC methodology: grants / (grants + denials)
            ROUND(
                100.0
                * COUNT(*) FILTER (WHERE a.appl_decision_normalized = 'GRT')
                / NULLIF(
                    COUNT(*) FILTER (
                        WHERE a.appl_decision_normalized IN ('GRT', 'DEN')
                    ), 0
                ), 2
            ) AS grant_rate_trac_pct,

            -- n for confidence interval calculation
            COUNT(*) FILTER (
                WHERE a.appl_decision_normalized IN ('GRT', 'DEN')
            ) AS n_merits_decisions

        FROM silver_applications a
        JOIN silver_proceedings p ON a.IDNPROCEEDING = p.IDNPROCEEDING
        JOIN silver_cases c       ON p.IDNCASE = c.IDNCASE
        WHERE a.APPL_TYPE = 'ASY'
          AND a.appl_decision_normalized IS NOT NULL
          AND c._current = TRUE
        GROUP BY 1, 2, 3, 4
    """)


def add_confidence_intervals(con: duckdb.DuckDBPyConnection) -> None:
    """
    Add Wilson score 95% confidence intervals.
    Suppress display for n < 30 — show 'Insufficient data' instead.
    Wilson score is preferred over naive Wald CI for proportions near 0 or 1.
    """
    con.execute("""
        CREATE OR REPLACE TABLE gold_asylum_rates AS
        SELECT
            *,
            ROUND(100.0 * (
                (grant_rate_trac_pct/100 + 1.96*1.96/(2*n_merits_decisions)
                 - 1.96 * SQRT(
                     grant_rate_trac_pct/100 * (1 - grant_rate_trac_pct/100)
                     / n_merits_decisions
                     + 1.96*1.96 / (4*n_merits_decisions*n_merits_decisions)
                   ))
                / (1 + 1.96*1.96/n_merits_decisions)
            ), 2) AS ci_lower_95,

            ROUND(100.0 * (
                (grant_rate_trac_pct/100 + 1.96*1.96/(2*n_merits_decisions)
                 + 1.96 * SQRT(
                     grant_rate_trac_pct/100 * (1 - grant_rate_trac_pct/100)
                     / n_merits_decisions
                     + 1.96*1.96 / (4*n_merits_decisions*n_merits_decisions)
                   ))
                / (1 + 1.96*1.96/n_merits_decisions)
            ), 2) AS ci_upper_95,

            CASE WHEN n_merits_decisions < 30
                 THEN TRUE ELSE FALSE END AS insufficient_data

        FROM gold_asylum_rates
    """)
```

---

## Part 8: Scheduling and Automation

```python
# scripts/scheduler.py
"""
Monthly pipeline runner. Recommended cron: 0 8 5 * *
(EOIR typically releases in the first week of each month)
"""

import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(f"logs/pipeline_{datetime.now().strftime('%Y-%m')}.log"),
        logging.StreamHandler(),
    ],
)


def run_monthly_pipeline():
    from scripts.download  import archive_release
    from scripts.diff      import diff_full_release, check_alerts
    from scripts.canonical import upsert_release, CANONICAL_DB, init_canonical
    from scripts.clean     import (clean_cases, normalize_application_outcomes,
                                   harmonize_pre_iirira_case_types)
    import duckdb
    import subprocess

    release_date = datetime.now().strftime("%Y-%m")
    bronze_base  = Path("bronze")

    logging.info("Step 1: Downloading new release...")
    curr_dir = archive_release()

    prev_releases = sorted([
        d for d in bronze_base.iterdir()
        if d.is_dir() and d.name != release_date
    ])

    if prev_releases:
        prev_dir = prev_releases[-1]
        logging.info(f"Step 2: Diffing {prev_dir.name} → {curr_dir.name}")
        summary = diff_full_release(prev_dir, curr_dir, Path("silver/diff_log"))
        alerts  = check_alerts(summary)

        if alerts:
            for a in alerts:
                logging.warning(a)
            logging.error(
                "PIPELINE HALTED: Anomalous deletion rates detected. "
                "Manual review required before publishing."
            )
            return  # Do NOT publish until reviewed
    else:
        logging.warning("No previous release found; skipping diff.")

    logging.info("Step 3: Updating canonical dataset...")
    con = duckdb.connect(str(CANONICAL_DB))
    init_canonical(con)
    upsert_release(con, curr_dir, release_date)

    logging.info("Step 4: Cleaning and harmonizing...")
    clean_cases(con)
    normalize_application_outcomes(con)
    harmonize_pre_iirira_case_types(con)

    logging.info("Step 5: Recomputing Gold metrics...")
    subprocess.run(["python", "scripts/aggregate.py"], check=True)

    logging.info(f"Pipeline complete for {release_date}.")
```

---

## Part 9: Publication Standards

### 9.1 Data Quality Disclosure (Required)

Every analytics site built on EOIR data must have a permanent, prominent **Data Quality / Methodology** page. This is the source of TRAC's credibility and is what separates a trustworthy site from one that publishes numbers without context. It should cover:

- The disappearing records problem: what years were affected, what TRAC found, and what you do about it
- Your archiving methodology (every release archived, never overwritten)
- Your diff methodology and the thresholds that pause publication
- How disappeared records are handled (preserved in canonical dataset, flagged in UI)
- The May 2019 application outcome code change and your normalization approach
- The pre-1997 IIRIRA terminology shift
- Scope limitations: expedited removal exclusions, paper cases, USCIS affirmative asylum
- Which grant rate denominator you use (TRAC methodology recommended) and why
- Recommended citation language

### 9.2 Display Rules for Judge Analytics

| Rule | Rationale |
|---|---|
| Suppress rates with n < 30 merits decisions | Avoid presenting statistically meaningless rates |
| Always show confidence intervals | A judge with 20 decisions should look different from one with 2,000 |
| Show date range on every rate | A rate from 2010–2024 is very different from 2023–2024 |
| State the denominator near every rate | "Grant rate = grants ÷ (grants + denials)" |
| Disclose exclusions | Administrative closures, abandonment, not_adjudicated excluded from denominator |
| Flag pre-1997 data on any chart crossing that boundary | Different terminology and case types |

### 9.3 Recommended Citation Language

```
Data: U.S. Department of Justice, Executive Office for Immigration Review (EOIR),
FOIA Library Case Data (monthly releases, [start date]–present).
Processed and analyzed by [Your Site Name].
Methodology: [your-site.com/methodology]
```

---

## Part 10: External Resources

### Official Sources

| Resource | URL |
|---|---|
| EOIR FOIA Library (monthly releases) | justice.gov/eoir/foia-library-0 |
| EOIR Workload & Adjudication Statistics | justice.gov/eoir/workload-and-adjudication-statistics |
| EOIR Statistical Yearbook (annual, back to 1990s) | justice.gov/eoir/statistical-year-book |
| EOIR Code Key | Included in the monthly FOIA zip file |
| EOIR Data Quality Guidelines (2024) | Search "EOIR Data Quality Guidelines 2024" on justice.gov |
| Data.gov mirror of EOIR Case Data | catalog.data.gov/dataset/eoir-case-data |

### Open Source Projects and Processed Data

| Resource | Description | URL |
|---|---|---|
| **Deportation Data Project** | Best single resource: processed data, full codebook, open-source R pipeline, monthly updates | deportationdata.org |
| **Deportation Data Project GitHub** | Full R processing code; every transformation decision is documented and replicable | github.com/UWCHR/deport-data-proj |
| **HuggingFace EOIR DuckDB** | Pre-built DuckDB with 164M rows / 97 tables; queryable via HTTP range requests (no download needed) | huggingface.co/datasets/ian-nason/eoir-database |
| **TRAC Immigration Tools** | Free public dashboards; the field's gold standard | tracreports.org/immigration |
| **OpenImmigration.us** | Judge-level public analytics with SQL transparency | openimmigration.us |
| **eoirdata.com** | Public EOIR case data explorer | eoirdata.com |
| **Mobile Pathways Dashboards** | Bond, asylum, motion, removal dashboards | mobilepathways.org/immigration-court-data |

### Reference and Documentation

| Resource | URL |
|---|---|
| EOIR Original Codebook (Deportation Data Project) | deportationdata.org/docs/eoir/codebook-original.html |
| EOIR Processed Codebook | deportationdata.org/docs/eoir/codebook-processed.html |
| EOIR Agency Documentation (FOIA-obtained data dicts) | deportationdata.org/docs/eoir/documents.html |
| GAO Report: Immigration Courts (2023) | gao.gov/products/gao-23-105431 |
| GAO Report: Asylum Outcome Variation (2008) | gao.gov/assets/a281805.html |
| TRAC Data Quality Reports | tracreports.org/immigration/reports/580 and /586 |
| Congressional Hispanic Caucus Letter (June 2020) | chc.house.gov (search "EOIR June 2020") |

### Python Libraries

```bash
pip install duckdb pandas pyarrow requests beautifulsoup4 openpyxl chardet
```

| Library | Purpose |
|---|---|
| `duckdb` | Primary analytical database; handles 30GB+ efficiently |
| `pandas` | Data loading and transformation |
| `pyarrow` | Parquet storage for Silver/Gold layers |
| `requests` + `beautifulsoup4` | Scraping the FOIA library for new release URLs |
| `openpyxl` | Reading the EOIR Code Key (often distributed as Excel) |
| `chardet` | Auto-detect encoding on ambiguous files |
| `zipfile` (stdlib) | Reliable extraction — do not use OS double-click |

### Quick Start: Pre-Processed Data (No ETL Required)

If you want to start querying before building the full pipeline, query the HuggingFace DuckDB directly:

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("""
    ATTACH 'https://huggingface.co/datasets/ian-nason/eoir-database/resolve/main/eoir.duckdb'
    AS eoir (READ_ONLY)
""")

# Example: top 10 courts by removal case volume
result = con.execute("""
    SELECT court_name, COUNT(*) AS cases
    FROM eoir.v_proceedings_full
    WHERE CASE_TYPE = 'RMV'
    GROUP BY court_name
    ORDER BY cases DESC
    LIMIT 10
""").df()
print(result)
```

Or use the Deportation Data Project's processed files (CSV, Stata, Feather, Parquet):

```python
import pandas as pd
import duckdb

# Download from deportationdata.org/data/processed/eoir.html
con = duckdb.connect()
con.execute("CREATE TABLE cases AS SELECT * FROM read_parquet('eoir_cases_processed.parquet')")

# Asylum grant rate by nationality, represented cases, 2015–2024, n >= 30
result = con.execute("""
    SELECT
        country_name,
        COUNT(*) FILTER (WHERE asylum_decision = 'Grant') AS grants,
        COUNT(*) FILTER (WHERE asylum_decision IN ('Grant','Deny')) AS n_merits,
        ROUND(100.0
            * COUNT(*) FILTER (WHERE asylum_decision = 'Grant')
            / NULLIF(COUNT(*) FILTER (WHERE asylum_decision IN ('Grant','Deny')), 0),
        2) AS grant_rate_pct
    FROM cases
    WHERE represented = TRUE
      AND nta_year BETWEEN 2015 AND 2024
    GROUP BY country_name
    HAVING n_merits >= 30
    ORDER BY n_merits DESC
""").df()
print(result)
```

---

## Summary Checklist

Before publishing any analysis on EOIR data, verify each item:

- [ ] Raw monthly releases are archived in dated folders and **never overwritten**
- [ ] Each new release has been **diffed against the prior one** before publication
- [ ] Deletion rates were checked against thresholds; pipeline halted if exceeded
- [ ] Deleted records are **preserved in canonical dataset**, not discarded
- [ ] Application outcome codes are **normalized** for the May 2019 change
- [ ] Pre-1997 records are **flagged** and handled if analysis crosses that boundary
- [ ] Grant rates use a **documented denominator** (TRAC methodology recommended)
- [ ] Judge-level rates are **suppressed below n=30** decisions
- [ ] **Confidence intervals** are computed and displayed on rate charts
- [ ] A **data quality / methodology page** is live and linked from every chart
- [ ] **Scope limitations** (expedited removal, paper cases, affirmative asylum) are disclosed
- [ ] **Citation language** is provided for users who want to reference the data

---

*Sources: TRAC at Syracuse University (tracreports.org); Deportation Data Project (deportationdata.org); EOIR FOIA Library; GAO Reports GAO-23-105431 and GAO-08-940; American Immigration Council; Congressional Hispanic Caucus*
