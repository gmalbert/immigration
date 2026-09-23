"""Mark rows from prior releases as _current=FALSE in extended canonical tables.

Equivalent to the per-release UPDATE that canonical.py would do at the end of
upsert_release, but applied directly to the existing canonical DB without
re-running the full 9-hour upsert. Safe to run repeatedly.
"""
import duckdb

DB = "silver/canonical.roadmap3.duckdb"
TABLES = [
    "canonical_nationalities",
    "canonical_bonds",
    "canonical_custody_history",
    "canonical_juvenile_history",
    "canonical_appeals",
    "canonical_fed_appeals",
    "canonical_three_member_referrals",
    "canonical_schedules",
    "canonical_charges",
    "canonical_rep_assignments",
    "canonical_attorneys",
    "canonical_motions",
]

con = duckdb.connect(DB)
for t in TABLES:
    if t not in {r[0] for r in con.execute("SHOW TABLES").fetchall()}:
        continue
    before = con.execute(f"SELECT COUNT(*) FROM {t} WHERE _current = TRUE").fetchone()[0]
    con.execute(f"UPDATE {t} SET _current = FALSE WHERE _last_seen_release != '2026-09'")
    after = con.execute(f"SELECT COUNT(*) FROM {t} WHERE _current = TRUE").fetchone()[0]
    print(f"  {t:<32}  _current=TRUE: {before:>12,} -> {after:>12,}")
con.execute("CHECKPOINT")
con.close()
print("done")
