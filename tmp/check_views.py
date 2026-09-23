import duckdb
con = duckdb.connect('silver/canonical.roadmap3.duckdb', read_only=True)
rows = con.execute("SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW' AND table_schema = 'main' ORDER BY 1").fetchall()
print('Views:', len(rows))
for (v,) in rows:
    n = con.execute('SELECT COUNT(*) FROM ' + v).fetchone()[0]
    print(' ', v.ljust(35), '->', f'{n:,} rows')
