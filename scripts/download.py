"""
scripts/download.py — Archive a monthly EOIR FOIA release.

Usage:
    python scripts/download.py

Saves the release to bronze/YYYY-MM/ with metadata and checksum.
Skips download if the current month's release is already archived.

EOIR does not publish a release calendar. Run this script monthly;
it will detect whether a new file is available vs. what's cached.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from pathlib import Path

from utils.eoir_api import (
    get_current_release_url,
    download_file,
    extract_eoir_zip,
    compute_sha256,
    write_release_metadata,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
BRONZE_DIR = ROOT / "bronze"


def archive_current_release() -> Path:
    """
    Download and archive the current EOIR monthly release.
    Returns the bronze release directory.
    """
    release_tag = datetime.now().strftime("%Y-%m")
    release_dir = BRONZE_DIR / release_tag

    # Check if already archived
    if (release_dir / "A_TblCase.txt").exists():
        log.info("Release %s already archived at %s", release_tag, release_dir)
        return release_dir

    log.info("Fetching EOIR FOIA page to discover download URL…")
    url = get_current_release_url()
    if not url:
        raise RuntimeError(
            "Could not find EOIR case data download URL on the FOIA library page.\n"
            "Check: https://www.justice.gov/eoir/foia-library-0"
        )

    log.info("Found download URL: %s", url)
    release_dir.mkdir(parents=True, exist_ok=True)

    zip_path = release_dir / "raw.zip"

    downloaded = 0

    def progress(dl, total):
        nonlocal downloaded
        if total:
            pct = dl / total * 100
            if int(pct) > int(downloaded / total * 100 if total else 0):
                log.info("  Downloading… %.1f%% (%d MB / %d MB)", pct, dl // 1024 // 1024, total // 1024 // 1024)
        downloaded = dl

    log.info("Downloading EOIR release (this may be several GB)…")
    download_file(url, zip_path, progress_callback=progress)

    log.info("Computing checksum…")
    sha256 = compute_sha256(zip_path)
    write_release_metadata(release_dir, url, sha256)

    log.info("Extracting ZIP…")
    extract_eoir_zip(zip_path, release_dir)

    log.info("Removing ZIP archive to recover disk space…")
    zip_path.unlink(missing_ok=True)

    log.info("✅ Release %s archived to %s", release_tag, release_dir)
    return release_dir


if __name__ == "__main__":
    archive_current_release()
