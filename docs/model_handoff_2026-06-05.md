# Next Model Handoff - 2026-06-05

[Back to README](../README.md)

This file is for the next model or contributor picking up the repo after the real-data pipeline refactor.

## Current State

The June 2026 EOIR CASE data has been downloaded locally, ingested, canonicalized, aggregated, and written to app-ready files under `data/`.

Verified real-data counts:

- `canonical_cases`: 12,552,603
- `canonical_proceedings`: 16,376,510
- `canonical_applications`: 15,921,543
- `canonical_bonds`: 1,603,097
- `canonical_custody_history`: 9,892,643
- `canonical_juvenile_history`: 2,971,242
- `canonical_appeals`: 1,487,013
- `canonical_fed_appeals`: 180,524
- `canonical_three_member_referrals`: 83,809
- `canonical_nationalities`: 251

`data/pipeline_status.json` reports:

- `last_release`: `2026-06`
- `seed_mode`: `false`
- `quality_warnings`: `0`

## What Was Implemented

- `scripts/ingest.py` now includes the dashboard's extended EOIR table set.
- `scripts/canonical.py` now supports:
  - custom `--canonical-db`
  - lower-memory DuckDB settings
  - fresh-load primary-key cleanup for blank/null-character keys
  - canonical tables for bonds, custody history, juvenile history, appeals, federal appeals, and three-member referrals
- `scripts/aggregate.py` now supports:
  - custom `--canonical-db`
  - real bond, detention, UAC, BIA/federal appeal, case-age, backlog-age, and removal-order outputs
- `pages/A_Policy_Appeals.py` avoids circuit-specific language that EOIR cannot support.
- `pages/C_Case_Processing.py` handles a one-year backlog snapshot.
- `pages/D_Respondents.py` clamps UAC year sliders to available real-data years.
- `README.md`, `docs/technical.md`, and `docs/real_data_roadmap.md` describe the real-data state.

## Verification Already Run

These checks passed:

```powershell
python -m py_compile cases.py pages\A_Policy_Appeals.py pages\B_Courts.py pages\C_Case_Processing.py pages\D_Respondents.py pages\E_Enforcement.py pages\F_Judges.py pages\G_Data_Quality.py utils\charts.py utils\data_loader.py utils\export.py utils\eoir_api.py utils\quality.py utils\__init__.py scripts\ingest.py scripts\canonical.py scripts\aggregate.py
```

```powershell
venv\Scripts\python.exe scripts\canonical.py --release 2026-06 --ingest-db silver\2026-06.core2.duckdb --canonical-db silver\canonical.roadmap3.duckdb
venv\Scripts\python.exe scripts\aggregate.py --canonical-db silver\canonical.roadmap3.duckdb
```

All generated Parquet files were checked for:

- non-empty row counts
- no duplicate column names
- PyArrow compatibility for Streamlit dataframes
- loader availability through `utils.data_loader`

The changed Streamlit pages were also executed in bare Python mode. Streamlit emitted expected `missing ScriptRunContext` warnings, but no page exceptions occurred.

## Files To Expect In Git Status

Expected tracked changes include:

- `README.md`
- `docs/technical.md`
- `docs/real_data_roadmap.md`
- `docs/repo_summary.md`
- `docs/model_handoff_2026-06-05.md`
- `docs/pipeline_diagram.md`
- `scripts/ingest.py`
- `scripts/canonical.py`
- `scripts/aggregate.py`
- `pages/A_Policy_Appeals.py`
- `pages/C_Case_Processing.py`
- `pages/D_Respondents.py`
- regenerated files in `data/`

Expected ignored local artifacts include:

- `bronze/`
- `silver/`
- `venv/`
- `__pycache__/`

## Watch Points

- Do not revert regenerated `data/` files unless intentionally returning to an older release.
- Do not commit `bronze/` or `silver/`; they are large local build artifacts.
- Avoid using `scripts/seed_data.py` for production output. It is useful only as historical/reference code.
- If a future EOIR release changes table names or columns, start in `scripts/ingest.py` table mapping and then check `scripts/canonical.py` column selections.
- If Streamlit reports slider range errors, compare the hardcoded default year to the actual min/max of the relevant Parquet file.
- If PyArrow reports duplicate columns, inspect display-dataframe construction on the page, not the Parquet file first.

## Best Next Improvements

- Add a small automated validation script that prints canonical counts, Parquet row counts, duplicate column checks, and pipeline status in one command.
- Add source-data caveat text directly into the affected UI sections for EOIR federal appeals and detention metrics.
- Consider external ICE/DHS data for true detention bed counts, average daily population, facility ownership, and cost.
- Consider monthly EOIR archives or yearbook aggregates for historical backlog trends.

