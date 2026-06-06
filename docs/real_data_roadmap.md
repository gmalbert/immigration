# Real Data Roadmap

[Back to README](../README.md)

This document tracks the dashboard sections that were moved from placeholder or seed-style files to real EOIR-generated data.

Current pipeline source: local June 2026 EOIR CASE release (`2026-06`).

Current status: implemented for EOIR-supported measures. A few measures still have explicit limits where EOIR does not publish the needed field in this CASE release.

## Implemented Outputs

| Area | Output files | EOIR source tables | Status |
| --- | --- | --- | --- |
| Bond analytics | `data/bond_analytics.parquet` | `D_TblAssociatedBond` | Real EOIR bond hearing counts, grant/denial proxy, and median bond amount. |
| Detention | `data/detention_timeline.parquet`, `data/detention_by_facility.parquet` | `tbl_CustodyHistory`, `A_TblCase`, `B_TblProceeding` | Real EOIR custody-history metrics. Facility file falls back to EOIR custody categories because facility type is not populated in this release. |
| BIA and federal appeals | `data/bia_timeline.parquet`, `data/circuit_appeals.parquet` | `tblAppeal`, `tblAppealFedCourts`, `tblThreeMbrReferrals` | Real EOIR appeal records. Federal appeal output is aggregated as a single EOIR federal-court category because circuit identity is not exposed in the table. |
| Unaccompanied children / juvenile history | `data/uac_metrics.parquet`, `data/uac_origin.parquet` | `tbl_JuvenileHistory`, `A_TblCase`, `B_TblProceeding`, `E_TblApplication` | Real EOIR juvenile-history metrics and nationality origin counts. |
| Case age and backlog age | `data/case_age_timeline.parquet`, `data/case_age_by_court.parquet`, `data/backlog_age_dist.parquet` | `A_TblCase`, `B_TblProceeding` | Real EOIR proceeding-age and pending-age aggregates. Historical backlog timeline remains a current-release snapshot unless monthly archives are added. |
| Removal orders | `data/removal_orders.parquet`, `data/removal_by_nationality.parquet` | `B_TblProceeding`, `tblLookupCourtDecision`, `tblLookupNationality` | Real EOIR proceeding decision aggregates by year and nationality. |

## Validation Counts

The canonical June 2026 build contains:

- 12,552,603 canonical cases
- 16,376,510 canonical proceedings
- 15,921,543 canonical applications
- 1,603,097 bond records
- 9,892,643 custody-history records
- 2,971,242 juvenile-history records
- 1,487,013 BIA appeal records
- 180,524 federal appeal records
- 83,809 three-member referral records

The generated `data/pipeline_status.json` reports `seed_mode: false`.

## Remaining Limits

These are not fake data, but they are limits of what the EOIR CASE release can prove by itself:

- True ICE average daily detention population and funded bed trends require ICE or DHS detention datasets.
- Facility ownership, facility cost, and precise facility names are not populated in the current EOIR CASE fields used by the app.
- Federal court appeal records in EOIR do not expose the circuit, so the app uses a single federal-court category rather than circuit-by-circuit rates.
- Historical backlog trends require monthly EOIR archives or EOIR yearbook aggregates. The current file shows the backlog state derivable from the June 2026 release.
- Removal/departure categories are based on EOIR immigration-court decision descriptions and do not include expedited removals handled outside immigration court.

## Rebuild Commands

```powershell
python scripts/download.py
python scripts/ingest.py --release 2026-06 --db-path silver\2026-06.core2.duckdb
python scripts/canonical.py --release 2026-06 --ingest-db silver\2026-06.core2.duckdb --canonical-db silver\canonical.roadmap3.duckdb
python scripts/aggregate.py --canonical-db silver\canonical.roadmap3.duckdb
```

The canonical script uses a conservative local DuckDB profile (`threads=1`, bounded memory) so the full release is more likely to complete on a normal workstation.
