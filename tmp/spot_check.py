"""Spot-check that aggregate outputs match canonical with _current=TRUE filter."""
import duckdb

con = duckdb.connect('silver/canonical.roadmap3.duckdb', read_only=True)

print('=== Self-consistency: filtered counts in canonical ===')
for table in ('canonical_charges', 'canonical_rep_assignments', 'canonical_schedules',
              'canonical_motions', 'canonical_bonds', 'canonical_custody_history',
              'canonical_juvenile_history', 'canonical_appeals', 'canonical_fed_appeals',
              'canonical_attorneys', 'canonical_nationalities'):
    cur = con.execute(f'SELECT COUNT(*) FROM {table} WHERE _current = TRUE').fetchone()[0]
    tot = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'  {table:<32}  _current=TRUE: {cur:>12,}  total: {tot:>12,}')

print()
print('=== bond_analytics sanity check ===')
fy_count = con.execute("""
    SELECT COUNT(DISTINCT
        CASE
            WHEN TRY_CAST(DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
            WHEN MONTH(TRY_CAST(DECISION_DATE AS TIMESTAMP)) >= 10
                THEN YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP)) + 1
            ELSE YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP))
        END
    ) FROM canonical_bonds
    WHERE _current = TRUE
      AND TRY_CAST(DECISION_DATE AS TIMESTAMP) IS NOT NULL
      AND YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP)) BETWEEN 1990 AND 2027
""").fetchone()[0]
print('Distinct fiscal_year from canonical_bonds (filtered):', fy_count, '(parquet has 37)')

print()
print('=== Compare to PRE-filter (should match since all rows are _current=TRUE) ===')
fy_count_unfiltered = con.execute("""
    SELECT COUNT(DISTINCT
        CASE
            WHEN TRY_CAST(DECISION_DATE AS TIMESTAMP) IS NULL THEN NULL
            WHEN MONTH(TRY_CAST(DECISION_DATE AS TIMESTAMP)) >= 10
                THEN YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP)) + 1
            ELSE YEAR(TRY_CAST(DECISION_DATE AS TIMESTAMP))
        END
    ) FROM canonical_bonds
""").fetchone()[0]
print('Distinct fiscal_year from canonical_bonds (unfiltered):', fy_count_unfiltered)

con.close()
