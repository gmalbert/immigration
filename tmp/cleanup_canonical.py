"""One-shot cleanup of accumulated June rows in extended canonical tables."""
import duckdb

DB = "silver/canonical.roadmap3.duckdb"

TABLES = [
    "canonical_charges",
    "canonical_rep_assignments",
    "canonical_schedules",
    "canonical_motions",
]

con = duckdb.connect(DB)
for t in TABLES:
    before = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    con.execute(f"DELETE FROM {t} WHERE _last_seen_release != '2026-09'")
    after = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {before:,} -> {after:,} rows")
con.execute("CHECKPOINT")
con.close()
print("done")
