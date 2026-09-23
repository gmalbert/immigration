import duckdb
con = duckdb.connect('silver/canonical.roadmap3.duckdb', read_only=True)
print('canonical_bonds _current distribution:')
for r in con.execute("SELECT _current, COUNT(*) FROM canonical_bonds GROUP BY _current").fetchall():
    print(' ', r)
print()
print('canonical_bonds _last_seen_release distribution:')
for r in con.execute("SELECT _last_seen_release, COUNT(*) FROM canonical_bonds GROUP BY _last_seen_release ORDER BY 1").fetchall():
    print(' ', r)
print()
print('canonical_attorneys _last_seen_release distribution:')
for r in con.execute("SELECT _last_seen_release, COUNT(*) FROM canonical_attorneys GROUP BY _last_seen_release ORDER BY 1").fetchall():
    print(' ', r)
