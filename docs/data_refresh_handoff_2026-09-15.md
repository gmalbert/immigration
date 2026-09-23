# EOIR Data Refresh Handoff

**Status as of 2026-09-20:** September 2026 release is live on the dashboard.

- `data/pipeline_status.json` → `last_release: "2026-09"`, `last_run: "2026-09-20T14:17:36"`.
- 12,821,419 cases / 16,817,345 proceedings / 16,370,145 applications.
- 10,830 historical rows marked `_ever_deleted` across the canonical cases/proceedings/applications.
- `data/*.parquet` regenerated 2026-09-20 14:17.

`scripts/refresh.py` is the single entry point for any future monthly refresh.

---

## Original handoff (2026-09-15)

The August 2026 EOIR CASE release had been downloaded, extracted, and ingested, but canonicalization, aggregation, validation, and staging were not completed. The dashboard was still on the June 2026 Gold-data snapshot.

## Completed

- Downloaded the current EOIR CASE archive from the FOIA library on 2026-09-05.
- The archive identifies itself as `EOIR Case Data 2026-0801`; it is stored in the ignored `bronze/2026-08/` directory.
- Recorded source metadata and SHA-256 checksum in `bronze/2026-08/metadata.txt`.
- Extracted the archive successfully.
- Ingested the dashboard's core tables into `silver/2026-08.core2.duckdb`.
- Ingest completed successfully at `2026-09-05 04:25:56`.

Selected August ingest counts:

| Table | Rows |
| --- | ---: |
| `A_TblCase` | 12,771,581 |
| `B_TblProceeding` | 16,730,625 |
| `E_TblApplication` | 16,282,469 |
| `tbl_schedule` | 47,614,429 |
| `tbl_RepsAssigned` | 26,681,318 |
| `B_TblProceedCharges` | 19,076,098 |

The ingest used the existing robust parser behavior. Some malformed `A_TblCase.csv` records were skipped by the fallback parser; this was logged, not fatal.

## Not Completed

- No August release was merged into the canonical database.
- No Gold Parquet/JSON outputs were regenerated.
- `data/pipeline_status.json` still reports `last_release: "2026-06"` and `last_run: "2026-06-05T22:49:14.668390"`.
- No generated files are staged, committed, pushed, or deployed.

## Resume From The Existing Ingest

Do **not** download the release again. From the repository root, use the new orchestrator:

```powershell
.\.venv\Scripts\python.exe scripts\refresh.py --release 2026-08 --stage canonical
.\.venv\Scripts\python.exe scripts\refresh.py --release 2026-08 --stage aggregate
```

Equivalently (and the recommended form going forward for any scheduled run):

```powershell
.\.venv\Scripts\python.exe scripts\refresh.py --release 2026-08
```

To inspect stage state at any time:

```powershell
.\.venv\Scripts\python.exe scripts\refresh.py --status
```

Then verify:

```powershell
Get-Content data\pipeline_status.json
git diff -- data
git status --short
```

Expected result: `pipeline_status.json` identifies `2026-08`, the generated files in `data/` have an August refresh timestamp, and only reviewable generated-data changes are staged. Do not commit, push, deploy, or create a pull request without explicit approval.

## Automation Note

The previous run launched `scripts/ingest.py` as a background process and the scheduled agent turn ended before `scripts/canonical.py` and `scripts/aggregate.py` ran, leaving the dashboard on the June 2026 Gold data despite an August ingest being on disk.

`scripts/refresh.py` is now the single entry point for any monthly refresh. It runs the four stages **synchronously** in the foreground, records per-release stage completion in `data/.pipeline_stages.json`, and short-circuits stages that are already marked done. Any scheduled job (heartbeat, cron, Task Scheduler, or agent invocation) should call only `refresh.py`. Backgrounding any stage inside the orchestrator will be treated as a bug.

## Bugs Fixed During This Refresh

1. **Canonical OOM (root cause of three failed runs).** `scripts/canonical.py` set `PRAGMA memory_limit='4GB'` and had no `temp_directory`. The September applications merge needs more than 4 GB of working memory for the UPDATE hash-join and the OS denies the allocation, producing `_duckdb.OutOfMemoryException` after 7 hours of partial progress. **Fix:** bump to `memory_limit='10GB'` and set `temp_directory=tmp/duckdb_canonical` so individual operators can spill.
2. **download.py ignores `--release`.** The script unconditionally uses `datetime.now().strftime("%Y-%m")` and has no `--release` flag. Passing `--release 2026-08` to the orchestrator downloaded the September release into `bronze/2026-09/` while still ingesting `bronze/2026-08/`. **Not yet patched.** Workaround: pass `--skip-download` to `refresh.py` if targeting a non-current release.
3. **Extended canonical tables accumulate per release.** `canonical_schedules`, `canonical_charges`, `canonical_rep_assignments`, `canonical_motions` use `DELETE … WHERE _last_seen_release = '<tag>'` + `INSERT` rather than `INSERT OR REPLACE`, so each monthly merge appended a full snapshot. `aggregate.py` queries them without filtering `_last_seen_release`, which would have double-counted every extended metric the moment a second release landed. **Not yet patched at the source.** One-shot cleanup in `tmp/cleanup_canonical.py` dropped June rows from the four accumulating tables before aggregate ran. The proper fix is to add `WHERE _last_seen_release = (SELECT MAX(_last_seen_release) FROM <table>)` (or equivalent) in `aggregate.py`, or to switch canonical.py to `INSERT OR REPLACE` for these tables.

## Open Follow-ups

- Patch `scripts/download.py` to accept `--release YYYY-MM`.
- Patch `aggregate.py` to filter extended tables by `MAX(_last_seen_release)`, or change canonical.py's extended-table logic to `INSERT OR REPLACE`, so future multi-release runs don't double-count.
- Decide where the `monthly-eoir-release-monitor` heartbeat lives (cron, Task Scheduler, or opencode agent) and point it at `refresh.py`.
