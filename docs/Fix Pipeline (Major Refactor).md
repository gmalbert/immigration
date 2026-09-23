Fix Pipeline (Major Refactor)
Update table name mappings for new EOIR format
Fix B_TblProceeding buffer overflow (increase chunk processing)
Map new table structures to old schema
Time: 2-4 hours
Risk: More EOIR schema changes


# Download EOIR data (stays local)
python scripts/download.py

# Process through pipeline
python scripts/ingest.py
python scripts/canonical.py  
python scripts/aggregate.py

# Result: data/*.parquet now has REAL data

# Gold: aggregated Parquet files
-data/*.parquet    # Remove this line - allow parquets to be committed
+# data/*.parquet  # Comment out - we want these committed now!

git add data/*.parquet
git commit -m "Add real EOIR aggregated data for instant deploys"
git push

git clone <your-repo>
cd immigration
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
streamlit run cases.py  # ← Real data, instant load!

fix EOIR Pipeline (Direct from EOIR)
Data Source: June 2026 EOIR release (what we just downloaded)

✅ Most current data - as fresh as EOIR publishes (monthly)
✅ Full control over ETL process
✅ Can customize processing
❌ Requires 2-4 hours to fix format issues
❌ May break again with future EOIR changes