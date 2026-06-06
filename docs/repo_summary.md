# Repo Summary

[Back to README](../README.md)

Relief Docket is a Streamlit dashboard for understanding public EOIR immigration court data. The app is designed for lay readers, so the committed `data/` outputs are small and fast to load, while the raw EOIR release and DuckDB build files stay local.

## Current Data State

- Source release: June 2026 EOIR CASE release (`2026-06`)
- Data mode: real EOIR pipeline output, not seed data
- Cases: 12,552,603
- Proceedings: 16,376,510
- Applications: 15,921,543
- Extended local side tables now include schedules, charges, representative assignments, attorneys, and motions
- App-ready outputs: committed files under `data/`
- Large local build artifacts: ignored under `bronze/` and `silver/`

`data/pipeline_status.json` is the authority for what the app reports at runtime.

## Main App Files

- `cases.py` - main Streamlit entry point and navigation
- `pages/A_Policy_Appeals.py` - policy trends, BIA appeals, EOIR federal appeal records
- `pages/B_Courts.py` - court-level metrics
- `pages/C_Case_Processing.py` - outcomes, backlog, case age
- `pages/D_Respondents.py` - nationalities, representation, juvenile/UAC metrics
- `pages/E_Enforcement.py` - in absentia, detention, removal, bond analytics
- `pages/F_Judges.py` - judge metrics and comparisons
- `pages/G_Data_Quality.py` - pipeline notes, quality notes, and preview of precomputed enhancement outputs
- `utils/data_loader.py` - loads `data/` Parquet and JSON files
- `utils/charts.py`, `utils/export.py`, `utils/quality.py` - shared UI helpers

## Pipeline Files

- `scripts/download.py` - downloads and extracts EOIR release files into `bronze/`
- `scripts/ingest.py` - loads selected EOIR tables into DuckDB
- `scripts/canonical.py` - builds canonical normalized tables in DuckDB
- `scripts/aggregate.py` - writes app-ready Parquet and JSON files into `data/`
- `scripts/diff.py` - compares monthly releases for records that changed or disappeared
- `scripts/seed_data.py` - old seed-data generator; do not use for production real data

## Rebuild Commands

Use the explicit paths below when Dropbox, OneDrive, antivirus software, or another sync tool may lock default DuckDB files:

```powershell
python scripts\download.py
python scripts\ingest.py --release 2026-06 --db-path silver\2026-06.core2.duckdb
python scripts\canonical.py --release 2026-06 --ingest-db silver\2026-06.core2.duckdb --canonical-db silver\canonical.roadmap3.duckdb
python scripts\aggregate.py --canonical-db silver\canonical.roadmap3.duckdb
```

The canonical script uses conservative DuckDB settings (`threads=1`, bounded memory) because the full local EOIR release is large.

## Precomputed Enhancement Outputs

The enhancement roadmap branch adds app-ready outputs for:

- annual judge, court, and nationality metrics
- representation impact by court and nationality
- case age by case type and judge
- hearing schedule and continuance metrics
- bond analytics by year, court, and judge
- custody transitions
- appeal outcomes by appeal type and filed-by party
- attorney/representative assignment aggregates
- charge analysis and charge outcomes
- motion activity
- release snapshot tracking
- data quality summary tables

These files are listed in [Data Enhancement Roadmap](data_enhancement_roadmap.md) and previewed in the Streamlit Data Quality page.

## Git Behavior

Commit:

- source code
- docs
- `data/*.parquet`
- `data/*.json`
- `data/pipeline_status.json`

Do not commit:

- `bronze/`
- `silver/`
- `venv/`
- `__pycache__/`
- `.duckdb` files
- raw EOIR downloads or scratch exports

## Important Source Limits

The app should not overclaim what EOIR can prove:

- EOIR federal appeal records do not expose circuit identity, so the app aggregates them as one federal-court category.
- EOIR custody history supports case-level custody metrics, but true ICE average daily population, bed counts, facility costs, and facility ownership require ICE/DHS datasets.
- Historical backlog trends require monthly EOIR archives or EOIR yearbook aggregates. The current backlog file is a current-release snapshot.
- Expedited removal usually happens outside immigration court, so removal outputs are immigration-court proceeding decisions.

## Future Data Work

See [Data Enhancement Roadmap](data_enhancement_roadmap.md) for the implemented bronze/silver-backed data additions and remaining caveats.
