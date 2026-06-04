"""
pages/G_Data_Quality.py — Data Quality & Transparency (standalone, identical to page 8)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from pathlib import Path

import streamlit as st
import pandas as pd

from utils import add_sidebar
from utils.data_loader import get_pipeline_status
from footer import add_gavel_glimpse_footer
from utils.quality import KNOWN_ISSUES, get_issues_by_severity

add_sidebar("data_quality")

ROOT = Path(__file__).parent.parent

st.title("🔍 Data Quality & Transparency")
st.markdown(
    "The EOIR CASE database is extraordinary in depth but documented in its quality problems. "
    "This page is our public commitment to transparency about what the data can and cannot tell you."
)

# ── Pipeline status ───────────────────────────────────────────────────────────
status = get_pipeline_status()

st.markdown("### Pipeline Status")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Last Release",     status.get("last_release", "—"))
col2.metric("Total Cases",      f"{status.get('total_cases', 0):,}")
col3.metric("Quality Warnings", str(status.get("quality_warnings", 0)))
col4.metric("Deletion Count",   f"{status.get('deletion_count', 0):,}",
            help="Records absent from a new release but preserved in canonical dataset")

if status.get("seed_mode"):
    st.info(
        "**Running in seed mode** — showing aggregate statistics from public sources. "
        "Individual judge, court, and case records are not loaded.",
        icon="ℹ️",
    )

# ── Known issues ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Known Data Quality Issues")
st.markdown(
    "These are documented, publicly known issues with the EOIR data — not speculation. "
    "Primary sources: TRAC at Syracuse University, GAO, Congressional investigations."
)

severity_icons = {"critical": "🚨", "high": "⚠️", "medium": "⚠", "low": "ℹ️"}
severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

for issue in sorted(KNOWN_ISSUES, key=lambda x: severity_order.get(x["severity"], 9)):
    icon = severity_icons.get(issue["severity"], "ℹ️")
    with st.expander(f"{icon} [{issue['severity'].upper()}] {issue['title']}"):
        st.markdown(f"**Problem:** {issue['summary']}")
        st.markdown(f"**Our mitigation:** {issue['mitigation']}")
        if issue.get("sources"):
            st.caption("Sources: " + " · ".join(issue["sources"]))

# ── Full pipeline instructions ────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Running the Full Pipeline")
st.markdown(
    "To enable individual judge, court, and case-level analytics, "
    "you need the full EOIR CASE database (~30GB uncompressed). "
    "Here is the complete pipeline:"
)
st.code("""
# Step 1: Download the latest EOIR monthly release from the FOIA library
python scripts/download.py

# Step 2: Load the raw tables into a DuckDB database
python scripts/ingest.py --release 2026-05

# Step 3 (optional): Diff against prior month for disappearing records
python scripts/diff.py --prev 2026-04 --curr 2026-05

# Step 4: Merge into the canonical Silver dataset (never deletes records)
python scripts/canonical.py --release 2026-05

# Step 5: Build Gold-layer Parquet files for the site
python scripts/aggregate.py

# Step 6: Restart the site
streamlit run cases.py
""", language="bash")

# ── Diff log viewer ───────────────────────────────────────────────────────────
diff_log_dir = ROOT / "silver" / "diff_log"
if diff_log_dir.exists():
    st.markdown("---")
    st.markdown("### Monthly Diff Logs")
    summary_files = sorted(diff_log_dir.glob("*_summary.csv"), reverse=True)
    if summary_files:
        selected_log = st.selectbox(
            "Select release to inspect",
            [f.name for f in summary_files],
            key="dq_log_select",
        )
        if selected_log:
            try:
                log_df = pd.read_csv(diff_log_dir / selected_log)
                from utils import clean_dataframe_columns
                st.dataframe(clean_dataframe_columns(log_df), width='stretch', hide_index=True)
                alerts = log_df[log_df.get("deletion_rate_pct", pd.Series(dtype=float)) > 0.1]
                if not alerts.empty:
                    st.error(
                        f"⚠ **{len(alerts)} tables** have elevated deletion rates in this release. "
                        "Review before publishing.",
                        icon="🚨",
                    )
                else:
                    st.success("No anomalous deletion rates in this release.", icon="✅")
            except Exception as e:
                st.warning(f"Could not read diff log: {e}")
    else:
        st.info("No diff logs found. Diff logs are created when running scripts/diff.py.")

# ── Data sources ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Data Sources & Further Reading")
st.markdown("""
| Source | What it provides | URL |
|---|---|---|
| EOIR FOIA Library | Raw monthly data downloads (primary source) | justice.gov/eoir/foia-library-0 |
| TRAC Immigration | Cleaned EOIR analysis; 15+ years of diff tracking | tracreports.org |
| Data.gov EOIR dataset | Mirrored with metadata | catalog.data.gov/dataset/eoir-case-data |
| Vera Institute | Representation rates dashboard | vera.org |
| Deportation Data Project | Processed EOIR data with codebook | deportationdata.org |
| HuggingFace EOIR DuckDB | Pre-built queryable 164M-row database | huggingface.co/datasets/ian-nason/eoir-database |
| EOIR Statistical Yearbook | Annual aggregate PDFs | justice.gov/eoir |
| GAO Immigration Reports | Independent quality assessments | gao.gov |
""")

st.caption(
    "Relief Docket is committed to publishing new diff logs with every monthly data update. "
    "If you find an anomaly or data quality issue not listed here, "
    "please open an issue on GitHub."
)

add_gavel_glimpse_footer()
