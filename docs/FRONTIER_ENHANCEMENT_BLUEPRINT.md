# Frontier Enhancement Blueprint

Existing documentation deeply covers EOIR ingestion, data quality, the bronze/silver/gold pipeline, descriptive dashboards, and data-source expansion. The next layer should emphasize uncertainty-aware longitudinal analysis, cautious causal designs, reproducible cohorts, and privacy.

## Time-to-event analysis

Case duration is censored for pending matters and contains competing outcomes. Replace completed-case averages with survival and competing-risk estimates for decision, administrative closure, termination, transfer, and appeal.

```python
from lifelines import CoxPHFitter

cols = ["duration_days", "decision_observed", "represented", "detained",
        "court_id", "filing_year"]
model = CoxPHFitter(penalizer=0.1).fit(df[cols], "duration_days", "decision_observed")
```

Do not interpret coefficients causally; show adjusted descriptive associations with uncertainty and cohort definitions.

## Multilevel estimates

Raw judge/court rates are unstable and confounded by case mix. Use hierarchical partial pooling across judge, court, nationality, representation, custody, application type, and time. Publish both observed and adjusted estimates, sample sizes, intervals, and shrinkage magnitude.

## Policy discontinuity notebooks

For policy changes, pre-register an interrupted-time-series or difference-in-differences design with falsification dates, parallel-trend diagnostics, compositional checks, and sensitivity bounds. Keep causal language out of the main dashboard unless assumptions and robustness are published.

## Reproducible cohort builder

Let users define a cohort with versioned filters and receive a stable URL/export containing data release, SQL/filter AST, suppression policy, and generated timestamp.

```python
cohort = {
  "release": "2026-06",
  "filters": [{"field": "case_type", "op": "in", "value": ["removal"]}],
  "as_of": "2026-06-30",
  "suppression_min_n": 20,
}
```

## Data and UI enhancements

- Event-sourced case histories with `effective_at`, `observed_at`, and correction lineage.
- Geographic access measures: travel time to court, accredited-representative deserts, detention transfers, and remote-hearing availability.
- Cohort-composition waterfall before any rate comparison.
- Uncertainty intervals and suppression for small cells; no league-table ranking of noisy judges.
- Methodology drawer tied to each chart and downloadable tidy data.
- Bilingual glossary and accessible non-color encodings.
- Privacy review for rare combinations and membership-inference risk before export.

## Validation gates

Reconcile event histories to published totals; test late-arriving updates and identifier churn; validate survival calibration over time; audit missingness and suppression by protected/meaningful groups; and require peer review of every causal claim. Version every gold table and surface its content hash in the UI.
