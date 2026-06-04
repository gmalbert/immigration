"""
Relief Docket – EOIR FOIA data access helpers.

Handles:
  - Discovering the current monthly release URL from the EOIR FOIA library page
  - Checking whether a new release is available vs. what's already archived
  - Downloading and extracting the release with EOIR-specific quirks handled
    (pipe-delimited, Windows-1252 encoding, ZIP extraction issues)
"""

import hashlib
import logging
import os
import csv
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

EOIR_FOIA_URL = "https://www.justice.gov/eoir/foia-library-0"
EOIR_STATS_URL = "https://www.justice.gov/eoir/workload-and-adjudication-statistics"
DATA_GOV_URL = "https://catalog.data.gov/dataset/eoir-case-data"
HEADERS = {
    "User-Agent": "ReliefDocket/1.0 (public immigration court analytics; contact via github)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 60


def get_current_release_url(foia_page_url: str = EOIR_FOIA_URL) -> Optional[str]:
    """
    Scrape the EOIR FOIA library page and return the bulk data download URL.
    Returns None if no link is found.
    """
    try:
        resp = requests.get(foia_page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".zip") and ("eoir" in href.lower() or "case" in href.lower()):
                if not href.startswith("http"):
                    href = "https://www.justice.gov" + href
                return href
    except Exception as e:
        log.warning("Could not fetch EOIR FOIA page: %s", e)
    return None


def get_workload_stats_links(stats_url: str = EOIR_STATS_URL) -> list[dict]:
    """
    Scrape the EOIR workload/adjudication statistics page for Excel/CSV download links.
    Returns list of {label, url} dicts.
    """
    results = []
    try:
        resp = requests.get(stats_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(href.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv")):
                if not href.startswith("http"):
                    href = "https://www.justice.gov" + href
                label = a.get_text(strip=True) or os.path.basename(href)
                results.append({"label": label, "url": href})
    except Exception as e:
        log.warning("Could not fetch EOIR stats page: %s", e)
    return results


def download_file(
    url: str,
    dest_path: Path,
    chunk_size: int = 1024 * 1024,
    progress_callback=None,
) -> Path:
    """
    Stream-download a file to dest_path.
    progress_callback(bytes_downloaded, total_bytes_or_None) called each chunk.
    Returns the path to the saved file.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        log.info("Already downloaded: %s", dest_path)
        return dest_path

    with requests.get(url, stream=True, headers=HEADERS, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) or None
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)

    return dest_path


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_eoir_zip(zip_path: Path, dest_dir: Path) -> None:
    """
    Extract EOIR's ZIP release.

    IMPORTANT: EOIR's zip may not extract with some OS tools.
    Python's zipfile module handles it reliably. If that fails,
    fall back: `7z x {zip_path} -o{dest_dir}`
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"Corrupt file in ZIP: {bad}")
            zf.extractall(dest_dir)
        log.info("Extracted to %s", dest_dir)
    except zipfile.BadZipFile as e:
        raise RuntimeError(
            f"EOIR zip extraction failed with Python zipfile: {e}\n"
            f"Try: 7z x {zip_path} -o{dest_dir}"
        ) from e


def write_release_metadata(release_dir: Path, source_url: str, checksum: str) -> None:
    """Write a metadata.txt file alongside the raw release files."""
    meta = (
        f"source_url: {source_url}\n"
        f"downloaded: {datetime.now().isoformat()}\n"
        f"sha256: {checksum}\n"
    )
    (release_dir / "metadata.txt").write_text(meta, encoding="utf-8")


# ── Table schema constants ────────────────────────────────────────────────────

# Primary keys for each major EOIR CASE table
EOIR_TABLE_PKS = {
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

# Alternative table names in newer EOIR releases (2024+)
# Maps old table name → list of alternative names to try
EOIR_TABLE_ALTERNATIVES = {
    "A_TblCase":           ["A_TblCase"],
    "B_TblProceeding":     ["B_TblProceeding"],
    "C_TblSchedule":       ["tbl_schedule"],
    "D_TblCharge":         ["B_TblProceedCharges"],
    "E_TblApplication":    ["tbl_Court_Appln"],
    "F_TblMotion":         ["tbl_Court_Motions"],
    "G_TblRepresentative": ["tbl_RepsAssigned", "tbl_EOIR_Attorney"],
    "H_TblCustodyHistory": ["tbl_CustodyHistory"],
    "I_TblBond":           ["D_TblAssociatedBond"],
    "J_TblJuvenile":       ["tbl_JuvenileHistory"],
    "K_TblLeadRider":      ["tbl_Lead_Rider"],
}

# EOIR files use pipe delimiter and Windows-1252 encoding
EOIR_ENCODING = "windows-1252"
EOIR_DELIMITER = "|"


def _find_eoir_file(release_dir: Path, table_name: str) -> tuple[Path | None, str, list | None]:
    """
    Find EOIR file path, delimiter, and columns for a table.
    Returns (file_path, delimiter, usecols) or (None, None, None) if not found.
    """
    # Build list of table names to try (primary + alternatives)
    table_names_to_try = [table_name]
    if table_name in EOIR_TABLE_ALTERNATIVES:
        table_names_to_try.extend(EOIR_TABLE_ALTERNATIVES[table_name])
    
    file_path = None
    delimiter = None
    
    for try_name in table_names_to_try:
        for ext, sep in ((".txt", EOIR_DELIMITER), (".csv", "\t")):
            direct = release_dir / f"{try_name}{ext}"
            if direct.exists():
                file_path = direct
                delimiter = sep
                break

            # EOIR's newer releases nest the data under
            # "EOIR Case Data YYYY-MMDD/EOIR Case Data/". Search recursively so
            # minor folder-name changes do not break the monthly pipeline.
            matches = list(release_dir.rglob(f"{try_name}{ext}"))
            if matches:
                file_path = matches[0]
                delimiter = sep
                break
        if file_path:
            break
    
    return file_path, delimiter, None


def load_eoir_table(
    release_dir: Path,
    table_name: str,
    usecols: Optional[list] = None,
) -> "pd.DataFrame":
    """
    Load a single EOIR table, handling both old (.txt pipe-delimited) and 
    new (.csv tab-delimited in nested directory) formats.
    Tries alternative table names if primary name not found.
    Returns an empty DataFrame on failure.
    """
    import pandas as pd

    file_path, delimiter, _ = _find_eoir_file(release_dir, table_name)
    
    if not file_path:
        log.warning("File not found for table: %s", table_name)
        return pd.DataFrame()

    # Special handling for very large files (B_TblProceeding ~3GB)
    # Use Python parser with chunking to avoid C parser buffer overflow
    use_chunked_reading = (table_name == "B_TblProceeding" or 
                           file_path.stat().st_size > 2_000_000_000)  # > 2GB
    
    if use_chunked_reading:
        log.info("Large file detected (%s MB), using chunked reading for %s",
                file_path.stat().st_size // 1024 // 1024, table_name)
        return _load_eoir_table_chunked(file_path, delimiter, table_name, usecols)

    read_kwargs = dict(
        sep=delimiter,
        low_memory=False,
        dtype=str,
        on_bad_lines="warn",
        usecols=usecols,
        quoting=csv.QUOTE_NONE,
        encoding_errors="replace",
    )
    
    for encoding in (EOIR_ENCODING, "latin-1", "utf-8"):
        try:
            df = pd.read_csv(file_path, encoding=encoding, **read_kwargs)
            df.columns = df.columns.str.strip().str.upper()
            df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)
            log.info("Loaded %s: %d rows from %s (encoding=%s)", 
                    table_name, len(df), file_path.name, encoding)
            return df
        except UnicodeDecodeError:
            log.warning("Encoding %s failed for %s, trying next…", encoding, table_name)
        except Exception as e:
            log.error("Failed to load %s from %s: %s", table_name, file_path.name, e)
            return pd.DataFrame()

    return pd.DataFrame()


def _load_eoir_table_chunked(
    file_path: Path,
    delimiter: str,
    table_name: str,
    usecols: Optional[list] = None,
) -> "pd.DataFrame":
    """
    Load a very large EOIR table using chunked reading with Python parser.
    Used for files > 2GB that cause C parser buffer overflows.
    """
    import pandas as pd
    
    read_kwargs = dict(
        sep=delimiter,
        engine="python",  # Python parser instead of C - slower but more robust
        dtype=str,
        on_bad_lines="skip",  # Skip malformed lines
        usecols=usecols,
        chunksize=100000,  # Read 100k rows at a time
        quoting=csv.QUOTE_NONE,
        encoding_errors="replace",
    )
    
    for encoding in (EOIR_ENCODING, "latin-1", "utf-8"):
        try:
            chunks = []
            row_count = 0
            log.info("Reading %s in chunks (encoding=%s)...", file_path.name, encoding)
            
            for i, chunk in enumerate(pd.read_csv(file_path, encoding=encoding, **read_kwargs)):
                chunk.columns = chunk.columns.str.strip().str.upper()
                chunk = chunk.apply(lambda col: col.str.strip() if col.dtype == object else col)
                chunks.append(chunk)
                row_count += len(chunk)
                
                if (i + 1) % 50 == 0:  # Log progress every 5M rows
                    log.info("  Processed %d rows so far...", row_count)
            
            if not chunks:
                log.warning("No data loaded from %s", file_path.name)
                return pd.DataFrame()
            
            df = pd.concat(chunks, ignore_index=True)
            log.info("Loaded %s: %d rows from %s (encoding=%s, chunked)", 
                    table_name, len(df), file_path.name, encoding)
            return df
            
        except UnicodeDecodeError:
            log.warning("Encoding %s failed for %s, trying next…", encoding, table_name)
        except Exception as e:
            log.error("Failed to load %s from %s: %s", table_name, file_path.name, e)
            return pd.DataFrame()
    
    return pd.DataFrame()


def load_eoir_table_to_duckdb(
    release_dir: Path,
    table_name: str,
    con: "duckdb.DuckDBPyConnection",
) -> int:
    """
    Load an EOIR table directly into DuckDB, streaming chunks for large files.
    Returns number of rows loaded.
    """
    import pandas as pd
    
    file_path, delimiter, usecols = _find_eoir_file(release_dir, table_name)
    if not file_path or not file_path.exists():
        log.warning("File not found for table %s in %s", table_name, release_dir)
        return 0
    
    def qident(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def sql_literal(path: Path) -> str:
        return "'" + path.as_posix().replace("'", "''") + "'"

    def duckdb_direct_load() -> int:
        """Load through DuckDB's CSV scanner with all columns preserved as text."""
        for encoding in ("utf-8", "latin-1"):
            try:
                con.execute(f"""
                    CREATE OR REPLACE TABLE {qident(table_name)} AS
                    SELECT * FROM read_csv(
                        {sql_literal(file_path)},
                        delim={delimiter!r},
                        header=true,
                        all_varchar=true,
                        encoding='{encoding}',
                        ignore_errors=false,
                        null_padding=true,
                        strict_mode=false,
                        sample_size=20480
                    )
                """)
                return con.execute(f"SELECT COUNT(*) FROM {qident(table_name)}").fetchone()[0]
            except Exception as e:
                log.warning("DuckDB direct load failed for %s (encoding=%s): %s", table_name, encoding, e)
        return 0

    direct_count = duckdb_direct_load()
    if direct_count:
        log.info("Loaded %s: %d rows (DuckDB CSV scanner)", table_name, direct_count)
        return direct_count

    file_size_mb = file_path.stat().st_size / (1024 ** 2)

    def stream_to_duckdb() -> int:
        """Stream a CSV/TXT file into DuckDB in chunks."""
        csv.field_size_limit(10 * 1024 * 1024)
        read_kwargs = dict(
            sep=delimiter,
            engine="python",
            dtype=str,
            on_bad_lines="skip",
            usecols=usecols,
            chunksize=100000,
            quoting=csv.QUOTE_NONE,
            encoding_errors="replace",
        )

        for encoding in (EOIR_ENCODING, "latin-1", "utf-8"):
            try:
                row_count = 0
                log.info("Reading %s in chunks (encoding=%s)...", file_path.name, encoding)

                for i, chunk in enumerate(pd.read_csv(file_path, encoding=encoding, **read_kwargs)):
                    chunk.columns = chunk.columns.str.strip().str.upper()
                    chunk = chunk.apply(lambda col: col.str.strip() if col.dtype == object else col)

                    con.register("_temp_chunk", chunk)
                    if i == 0:
                        con.execute(f"CREATE OR REPLACE TABLE {qident(table_name)} AS SELECT * FROM _temp_chunk")
                    else:
                        con.execute(f"INSERT INTO {qident(table_name)} SELECT * FROM _temp_chunk")

                    row_count += len(chunk)

                    if (i + 1) % 50 == 0:
                        log.info("  Processed %d rows so far...", row_count)

                log.info("Loaded %s: %d rows (streamed to DuckDB)", table_name, row_count)
                return row_count

            except UnicodeDecodeError:
                log.warning("Encoding %s failed for %s, trying next…", encoding, table_name)
            except Exception as e:
                log.error("Failed to stream %s to DuckDB: %s", table_name, e)
                try:
                    con.execute(f"DROP TABLE IF EXISTS {qident(table_name)}")
                except Exception:
                    pass
                return 0

        return 0
    
    # For very large files (>2GB), stream chunks directly to DuckDB
    if file_size_mb > 2000:
        log.info("Large file detected (%.0f MB), streaming to DuckDB in chunks for %s", file_size_mb, table_name)

        return stream_to_duckdb()

    # For smaller files, try the normal loader first, then fall back to streaming
    df = load_eoir_table(release_dir, table_name)
    if not df.empty:
        con.register(f"_df_{table_name}", df)
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _df_{table_name}")
        return len(df)

    log.warning("Falling back to streamed load for %s after pandas load failed or returned empty", table_name)
    return stream_to_duckdb()
