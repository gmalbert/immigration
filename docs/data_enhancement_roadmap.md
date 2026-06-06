# Data Enhancement Roadmap

[Back to README](../README.md)

This roadmap lists suggested dashboard/data improvements that can be built from the local `bronze/` and `silver/` data layers.

Priority is based on:

- User value for a public-facing dashboard
- Whether the needed data already exists in the June 2026 EOIR release
- Implementation difficulty
- Risk of overclaiming what EOIR can prove

Ease scale:

- Easy: mostly a new aggregate query and UI/table update
- Medium: requires new canonical joins, careful definitions, or page design
- Hard: requires substantial modeling, validation, or external/monthly data

## Priority 1: Judge Metrics By Fiscal Year

Source layer: `silver`

Likely tables:

- `canonical_proceedings`
- `canonical_applications`
- `canonical_cases`

What to add:

- `judge_metrics_by_year.parquet`
- Annual judge caseload, grant rate, removal rate, in absentia rate, and representation rate
- Ability to show whether a judge's outcomes changed over time

Why it matters:

The current judge file is mostly all-time. Annual trends would make the judge page more useful and prevent old cases from overwhelming current patterns.

Ease: Medium

Main work:

- Add fiscal-year grouping to the existing judge aggregate.
- Add minimum-case thresholds so small yearly samples are not misleading.
- Update judge page to show trend lines for selected judges.

Risks:

- Some judge-year cells will have very low case counts.
- Raw rates still do not control for case mix, nationality, detention, or representation.

## Priority 2: Court Metrics By Fiscal Year

Source layer: `silver`

Likely tables:

- `canonical_proceedings`
- `canonical_applications`
- `canonical_cases`

What to add:

- `court_metrics_by_year.parquet`
- Annual court caseload, pending/completion counts, grant rate, representation rate, in absentia rate, removal rate

Why it matters:

This would make court trends more meaningful and would support maps/charts that show how court behavior changes over time.

Ease: Easy to Medium

Main work:

- Extend the current court aggregate with `fiscal_year`.
- Add trend UI to the courts page.

Risks:

- Court names and hearing locations can change.
- Some courts may have small or intermittent caseloads.

## Priority 3: Nationality Outcomes By Year

Source layer: `silver`

Likely tables:

- `canonical_cases`
- `canonical_proceedings`
- `canonical_applications`
- `canonical_nationalities`

What to add:

- `nationality_metrics_by_year.parquet`
- Yearly case counts, asylum grant rate, representation rate, removal rate by nationality

Why it matters:

Nationality is one of the most important drivers of immigration court outcomes. Annual trends would help distinguish long-term patterns from one-release totals.

Ease: Easy to Medium

Main work:

- Add fiscal-year grouping to nationality aggregate.
- Add thresholds to hide tiny groups.
- Update respondent/nationality UI.

Risks:

- Nationality mix and case type mix can change a lot year to year.
- Public language should avoid implying nationality alone causes outcomes.

## Priority 4: Representation Impact By Court And Nationality

Source layer: `silver`

Likely tables:

- `canonical_cases`
- `canonical_proceedings`
- `canonical_applications`
- `canonical_nationalities`

What to add:

- `representation_by_court.parquet`
- `representation_by_nationality.parquet`
- Comparison of outcomes for represented vs pro se respondents

Why it matters:

The representation gap is one of the clearest, most understandable public-interest findings in immigration court data.

Ease: Medium

Main work:

- Build grouped aggregates by court and nationality.
- Add minimum denominators for represented and unrepresented groups.
- Add careful notes about correlation versus causation.

Risks:

- Representation is not randomly assigned.
- Represented respondents may differ from unrepresented respondents in case type, nationality, detention status, and procedural posture.

## Priority 5: Case Age By Court, Judge, And Case Type

Source layer: `silver`

Likely tables:

- `canonical_proceedings`
- `canonical_cases`

What to add:

- `case_age_by_case_type.parquet`
- `case_age_by_judge.parquet`
- More detailed medians and percentiles for completed and pending matters

Why it matters:

Processing time is a major public concern. Users will want to know where cases take longest and whether delays differ by court, judge, or case type.

Ease: Medium

Main work:

- Define start date consistently (`INPUT_DATE`, `OSC_DATE`, or another field).
- Define completion date consistently.
- Add pending-age and completed-age variants.

Risks:

- Multiple proceedings per case can complicate "case age."
- Reopened, transferred, or venue-changed cases need careful handling.

## Priority 6: Hearing Schedule And Continuance Metrics

Source layer: `bronze` then `silver`

Likely tables:

- `tbl_schedule`
- `canonical_proceedings`
- possibly `tbl_Court_Motions`

What to add:

- Hearing count per proceeding
- Time between hearings
- Number of continuances or resets if reliably inferable
- No-show/hearing outcome patterns if supported

Why it matters:

This would explain why cases take years: repeated hearings, adjournments, and scheduling gaps are often the mechanism behind delay.

Ease: Medium to Hard

Main work:

- Add schedule table to canonical model.
- Determine which schedule fields are reliable.
- Define continuance/reschedule logic.

Risks:

- Schedule data can be messy.
- It may be hard to distinguish continuance reasons without external context.

## Priority 7: Bond Analytics By Court, Judge, And Year

Source layer: `silver`

Likely tables:

- `canonical_bonds`
- `canonical_proceedings`
- `canonical_cases`

What to add:

- `bond_by_court.parquet`
- `bond_by_judge.parquet`
- `bond_by_year.parquet`
- Median and percentile bond amounts, grant/denial proxy, hearing volumes

Why it matters:

Bond outcomes are high-impact and understandable. They also connect detention status to court decision-making.

Ease: Medium

Main work:

- Refine decision-code mapping for granted, denied, withdrawn, redetermined, and unknown.
- Add percentiles, not just medians.
- Add court/judge filters with minimum sample sizes.

Risks:

- Bond decision fields need validation.
- Bond amount populatedness may vary.
- "Denied" may not always equal a simple zero/blank bond amount.

## Priority 8: Custody Transitions And Detention Timeline

Source layer: `silver`

Likely tables:

- `canonical_custody_history`
- `canonical_cases`
- `canonical_proceedings`

What to add:

- `custody_transitions.parquet`
- detained-to-released counts
- release timing
- custody status at decision

Why it matters:

Current detention outputs are real but broad. Transitions would better explain how detention status changes during a case.

Ease: Medium to Hard

Main work:

- Order custody events by case/date.
- Build transition states.
- Join to decision outcomes.

Risks:

- EOIR custody history is not the same as ICE detention population data.
- True average daily population, bed counts, facility ownership, and cost require external ICE/DHS data.

## Priority 9: Appeal Outcomes By Appeal Type And Filed-By Party

Source layer: `silver`

Likely tables:

- `canonical_appeals`
- `canonical_fed_appeals`
- `canonical_three_member_referrals`

What to add:

- BIA appeal outcomes by appeal category/type
- Respondent vs DHS appeal rates
- Remand/sustain/dismiss patterns
- Three-member referral counts

Why it matters:

Appeals are currently real but high-level. More detail would make the policy/appeals page much more informative.

Ease: Medium

Main work:

- Validate appeal outcome codes and text fields.
- Decide how `tblAppeal` and `tblAppeal2` should be reconciled.
- Add clear categories and caveats.

Risks:

- Federal appeal records do not expose circuit identity in the current EOIR table.
- Some fields may be sparse or difficult to interpret.

## Priority 10: Attorney And Representation Detail

Source layer: `bronze` then `silver`

Likely tables:

- `tbl_RepsAssigned`
- `tbl_EOIR_Attorney`
- `canonical_cases`
- `canonical_proceedings`

What to add:

- Representation timing
- Attorney/representative assignment counts
- Organization or representative-type metrics if safely available

Why it matters:

The current app mostly treats representation as yes/no. More detail could show when representation appears and whether it changes outcomes.

Ease: Hard

Main work:

- Add representative tables to canonical model.
- Determine privacy and public-display boundaries.
- Avoid exposing individual attorney-level rankings unless carefully justified.

Risks:

- Privacy/reputational concerns.
- Data may identify individual representatives.
- Public app should likely aggregate this carefully.

## Priority 11: Charge-Level Analysis

Source layer: `bronze` then `silver`

Likely tables:

- `B_TblProceedCharges`
- `canonical_proceedings`

What to add:

- Most common charge grounds
- Outcomes by charge category
- Charge mix by nationality/court/year

Why it matters:

Charges help explain why outcomes differ. This would improve causal context.

Ease: Medium to Hard

Main work:

- Ingest/canonicalize proceeding charges.
- Map legal charge codes to readable categories.
- Add careful explanatory text.

Risks:

- Legal code mapping may be complex.
- High risk of confusing readers without strong plain-English explanations.

## Priority 12: Motion Activity

Source layer: `bronze` then `silver`

Likely tables:

- `tbl_Court_Motions`
- `canonical_proceedings`

What to add:

- Motions filed by type/year/court
- Motion outcomes if available
- Motion activity as a complexity proxy

Why it matters:

Motion activity can explain delays and procedural complexity.

Ease: Hard

Main work:

- Inspect and canonicalize motion fields.
- Validate motion outcome semantics.
- Decide which motion categories are meaningful for public users.

Risks:

- Motion data may be sparse or hard to interpret.
- Requires careful legal labeling.

## Priority 13: Monthly Snapshot Tracking

Source layer: repeated `bronze` and `silver` releases

Likely tables:

- all canonical core tables across multiple monthly EOIR releases

What to add:

- Monthly backlog history
- Records added/removed/changed each release
- Volatility and data-quality monitoring

Why it matters:

This is the only honest way to reconstruct how the EOIR database changes month to month.

Ease: Hard

Main work:

- Preserve every monthly EOIR release.
- Run ingest/canonical for each release.
- Use `scripts/diff.py` or an expanded diff pipeline.
- Store release-level snapshots or deltas.

Risks:

- Large storage requirements.
- More complex rebuilds.
- EOIR may change schemas between releases.

## Priority 14: Data Quality Audit Tables

Source layer: `bronze` and `silver`

Likely tables:

- all ingested/canonical tables

What to add:

- Missingness by field/table
- Dirty code counts
- Null-character/blank-value counts
- Duplicate primary-key audit
- Ingest row counts versus canonical row counts

Why it matters:

This improves trust. It also helps future maintainers understand why some numbers changed.

Ease: Easy to Medium

Main work:

- Add a validation script.
- Write `data/data_quality_summary.parquet` or JSON.
- Surface a plain-English version on the Data Quality page.

Risks:

- Audit numbers can alarm users if not explained well.

## Recommended Build Order

1. Data quality audit tables
2. Court metrics by fiscal year
3. Judge metrics by fiscal year
4. Nationality outcomes by year
5. Representation impact by court and nationality
6. Bond analytics by court, judge, and year
7. Case age by court, judge, and case type
8. Appeal outcomes by type and filed-by party
9. Custody transitions
10. Hearing schedule and continuance metrics
11. Charge-level analysis
12. Attorney/representative detail
13. Motion activity
14. Monthly snapshot tracking

## General Rule

Use `bronze/` to discover and verify raw EOIR fields. Use `silver/` to build stable canonical joins and aggregates. Commit only small, documented outputs in `data/`.
