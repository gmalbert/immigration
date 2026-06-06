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
- `canonical_schedules`: 45,806,542
- `canonical_charges`: 18,671,152
- `canonical_rep_assignments`: 25,944,715
- `canonical_attorneys`: 405,545
- `canonical_motions`: 8,314,085

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
  - canonical tables for bonds, custody history, juvenile history, appeals, federal appeals, three-member referrals, schedules, charges, representative assignments, attorneys, and motions
- `scripts/aggregate.py` now supports:
  - custom `--canonical-db`
  - real bond, detention, UAC, BIA/federal appeal, case-age, backlog-age, removal-order, schedule, continuance, charge, motion, representation-detail, annual trend, quality-audit, and release-snapshot outputs
- `utils/data_loader.py` exposes generic loading and metadata for implemented roadmap outputs.
- `pages/G_Data_Quality.py` previews the new precomputed enhancement tables.
- `pages/A_Policy_Appeals.py` avoids circuit-specific language that EOIR cannot support.
- `pages/C_Case_Processing.py` handles a one-year backlog snapshot.
- `pages/D_Respondents.py` clamps UAC year sliders to available real-data years.
- `README.md`, `docs/technical.md`, and `docs/real_data_roadmap.md` describe the real-data state.

## Verification Already Run

These checks passed before the enhancement branch. Rerun the compile command after any further code edits:

```powershell
python -m py_compile cases.py pages\A_Policy_Appeals.py pages\B_Courts.py pages\C_Case_Processing.py pages\D_Respondents.py pages\E_Enforcement.py pages\F_Judges.py pages\G_Data_Quality.py utils\charts.py utils\data_loader.py utils\export.py utils\eoir_api.py utils\quality.py utils\__init__.py scripts\ingest.py scripts\canonical.py scripts\aggregate.py
```

```powershell
venv\Scripts\python.exe scripts\aggregate.py --canonical-db silver\canonical.roadmap3.duckdb
```

The full aggregate command above passed on this branch at `2026-06-05 22:49`, writing all core and roadmap Parquet/JSON outputs with no errors.

All generated Parquet files were checked for:

- non-empty row counts
- no duplicate column names
- PyArrow compatibility for Streamlit dataframes
- loader availability through `utils.data_loader`

The changed Streamlit pages were also executed in bare Python mode. Streamlit emitted expected `missing ScriptRunContext` warnings, but no page exceptions occurred.

Roadmap tail-builder verification passed after the charge outcome query was optimized:

```powershell
venv\Scripts\python.exe -c "from pathlib import Path; from scripts.aggregate import get_con, build_extended_event_outputs, build_quality_and_snapshot_outputs, write_pipeline_status; con=get_con(Path('silver/canonical.roadmap3.duckdb')); build_extended_event_outputs(con); build_quality_and_snapshot_outputs(con); write_pipeline_status(con); con.close()"
```

That command wrote `charge_outcomes.parquet`, `motion_activity.parquet`, `representation_details.parquet`, `data_quality_summary.parquet`, `release_snapshot_tracking.parquet`, and `pipeline_status.json`.

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
- `utils/data_loader.py`
- `pages/G_Data_Quality.py`
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
- Consider external ICE/DHS data for true detention bed counts, average daily population, facility ownership, and cost.
- Consider monthly EOIR archives or yearbook aggregates for historical backlog trends.
