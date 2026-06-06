# Technical Notes

[Back to README](../README.md)

This page is for people who want to understand or rebuild the data pipeline behind Relief Docket.

For the detailed implementation status of the secondary real-data sections, see [Real Data Roadmap](real_data_roadmap.md).

## Running The App

Create a virtual environment, install dependencies, and start Streamlit:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
streamlit run cases.py
```

The app should open in your browser. Because the small Parquet files in `data/` are committed, the dashboard can load immediately without downloading the full EOIR database.

## Repository Layout

- `cases.py` - main Streamlit app
- `pages/` - dashboard pages
- `utils/` - shared charting, loading, and display helpers
- `scripts/download.py` - downloads the EOIR release
- `scripts/ingest.py` - loads EOIR tables into DuckDB
- `scripts/canonical.py` - builds the normalized canonical database
- `scripts/aggregate.py` - writes small Parquet files for the app
- `data/` - committed app-ready data files
- `docs/technical.md` - technical pipeline notes and rebuild instructions
- `docs/` - deeper notes on data quality and pipeline work

## Pipeline Summary

Relief Docket uses a three-layer data pipeline:

- `bronze/` - raw EOIR release files, downloaded and extracted locally
- `silver/` - DuckDB databases used for ingest and canonical normalization
- `data/` - small Parquet and JSON files used directly by the Streamlit app

Only `data/` is intended to be committed. The raw EOIR release and DuckDB databases are large local build artifacts and are ignored by Git.

## Current Release

The current committed app data was generated from the June 2026 EOIR release.

Current pipeline status:

- Release tag: `2026-06`
- Cases: `12,552,603`
- Proceedings: `16,376,510`
- Applications: `15,921,543`
- Seed mode: `false`

The app reads this status from `data/pipeline_status.json`.

## Core Tables

The current real-data build uses these EOIR tables for the dashboard:

- `A_TblCase`
- `B_TblProceeding`
- `E_TblApplication`
- `tblLookupHloc`
- `tblLookupJudge`
- `tblLookupCourtDecision`
- `tblLookUp_Appln`
- `tblLookupNationality`
- `D_TblAssociatedBond`
- `tbl_CustodyHistory`
- `tbl_JuvenileHistory`
- `tblAppeal`
- `tblAppeal2`
- `tblAppealFedCourts`
- `tblThreeMbrReferrals`

The ingest script defaults to this dashboard table set. Use `--all` only when you need broader EOIR coverage.

## Rebuild From EOIR

From the repository root:

```powershell
python scripts\download.py
python scripts\ingest.py --release 2026-06 --db-path silver\2026-06.core2.duckdb
python scripts\canonical.py --release 2026-06 --ingest-db silver\2026-06.core2.duckdb --canonical-db silver\canonical.roadmap3.duckdb
python scripts\aggregate.py --canonical-db silver\canonical.roadmap3.duckdb
```

The explicit database paths keep the large generated DuckDB files separate from any default file that may be locked by Dropbox, OneDrive, antivirus software, or another sync process.

For a simpler rebuild on a machine without file-locking issues, the same scripts can be run with their default paths:

```powershell
python scripts\ingest.py --release 2026-06
python scripts\canonical.py --release 2026-06
python scripts\aggregate.py
```

## Optional Full Ingest

To ingest every table listed in `EOIR_TABLE_PKS`, run:

```powershell
python scripts\ingest.py --release 2026-06 --all
```

This can take much longer and requires more disk space. It is not required for the current dashboard’s core real-data pages.

## Key Scripts

- `scripts/download.py` discovers and downloads the latest EOIR FOIA release.
- `scripts/ingest.py` loads EOIR tables into DuckDB.
- `scripts/canonical.py` normalizes EOIR tables into stable canonical tables.
- `scripts/aggregate.py` writes app-ready Parquet and JSON files.
- `scripts/diff.py` compares monthly releases for disappeared records.

## Important Implementation Details

EOIR file formats have changed over time. The loader handles:

- legacy `.txt` files
- newer nested `.csv` files
- pipe-delimited legacy exports
- tab-delimited newer exports
- alternate table names introduced in newer releases
- malformed or non-UTF text in large EOIR files

Large tables are loaded with DuckDB first. If DuckDB rejects a file because of encoding or parser issues, the loader falls back to streaming chunks into DuckDB through pandas.

## Canonical Model

The canonical database is designed to avoid destructive deletion.

Records are inserted or updated with provenance fields:

- `_first_seen_release`
- `_last_seen_release`
- `_current`
- `_ever_deleted`
- `_deletion_releases`

If a record disappears from a later EOIR release, it should be marked rather than physically removed. This mirrors the project’s transparency goal: readers should know when records appear, disappear, or change.

## Gold Outputs

The Streamlit app reads the small files in `data/`, including:

- `judge_metrics.parquet`
- `court_metrics.parquet`
- `nationality_metrics.parquet`
- `case_outcomes.parquet`
- `representation_gap.parquet`
- `policy_trends.parquet`
- `in_absentia_timeline.parquet`
- `in_absentia_by_court.parquet`
- `bond_analytics.parquet`
- `detention_timeline.parquet`
- `detention_by_facility.parquet`
- `uac_metrics.parquet`
- `uac_origin.parquet`
- `bia_timeline.parquet`
- `circuit_appeals.parquet`
- `case_age_timeline.parquet`
- `case_age_by_court.parquet`
- `backlog_age_dist.parquet`
- `removal_orders.parquet`
- `removal_by_nationality.parquet`
- `pipeline_status.json`

The committed Parquet files are generated from EOIR data, not seed data. Some measures remain limited by what EOIR publishes in the CASE release; see [Real Data Roadmap](real_data_roadmap.md) for those caveats.

## Git Notes

The intended Git behavior is:

- Commit source code, pages, utilities, docs, requirements, app assets, and `data/`.
- Do not commit `bronze/`, `silver/`, virtual environments, logs, or local DuckDB files.
- Commit `data/pipeline_status.json` so deployments know whether the app is using seed or real data.

[Back to README](../README.md)
