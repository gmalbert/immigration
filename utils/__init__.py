"""
Relief Docket – shared UI helpers.
"""
import os
import json
from datetime import date as _date

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def add_sidebar(page_key: str = ""):
    """Render the sidebar: data-freshness badge + navigation context."""
    import streamlit as st

    # ── Data status badge ────────────────────────────────────────────────────
    status_path = os.path.join(_ROOT, "data", "pipeline_status.json")
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as f:
                status = json.load(f)
            last_release = status.get("last_release", "")
            rows = status.get("total_cases", 0)
            quality_warnings = status.get("quality_warnings", 0)

            if last_release:
                try:
                    days_old = (_date.today() - _date.fromisoformat(last_release)).days
                    age_str = "today" if days_old == 0 else f"{days_old}d ago"
                except ValueError:
                    age_str = last_release

                badge_color = "#1e8a50" if quality_warnings == 0 else "#c87800"
                st.sidebar.markdown(
                    f"""
                    <div style="background:{badge_color};color:white;padding:6px 10px;
                                border-radius:6px;font-size:12px;text-align:center;margin-bottom:8px;">
                        📊 Data: <strong>{last_release}</strong> &nbsp;·&nbsp; {age_str}<br>
                        {f"⚠ {quality_warnings} quality warning(s)" if quality_warnings else f"✅ {int(rows):,} cases"}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        except Exception:
            pass
    else:
        st.sidebar.markdown(
            """
            <div style="background:#888;color:white;padding:6px 10px;
                        border-radius:6px;font-size:12px;text-align:center;margin-bottom:8px;">
                ⚙️ No data loaded yet<br>
                <small>Run <code>seed_data.py</code> to start</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Logo + Disclaimer ───────────────────────────────────────────────
    st.sidebar.markdown("---")
    # Suppress logo on home page (it's shown in main area), show larger on other pages
    if page_key != "home":
        st.sidebar.image(os.path.join(_ROOT, "data_files", "logo_transparent.png"), width=240)
    st.sidebar.caption(
        "**Relief Docket** — public immigration court analytics. "
        "For informational and research purposes only. Not legal advice."
    )


def no_data_banner(pipeline_step: str = "seed_data.py") -> None:
    """Show a standard 'data not loaded' warning."""
    import streamlit as st

    st.warning(
        f"**No data loaded yet.** "
        f"Run `python scripts/{pipeline_step}` to download and process the initial dataset, "
        f"then refresh this page.",
        icon="⚙️",
    )


def format_pct(val, decimals: int = 1) -> str:
    """Format a float 0–1 as a percentage string."""
    if val is None:
        return "—"
    return f"{val * 100:.{decimals}f}%"


def format_num(val) -> str:
    """Format an integer with commas."""
    if val is None:
        return "—"
    return f"{int(val):,}"


def clean_column_name(col: str) -> str:
    """Convert snake_case column name to Title Case for display."""
    return col.replace("_", " ").title()


def clean_dataframe_columns(df):
    """Return DataFrame with cleaned column names (Title Case, no underscores)."""
    import pandas as pd
    df_display = df.copy()
    df_display.columns = [clean_column_name(c) for c in df_display.columns]
    return df_display


def csv_download_button(df, filename: str, label: str = "⬇ Download CSV", key: str = None) -> None:
    """Render a Streamlit download button for a DataFrame as CSV."""
    import streamlit as st

    if df is None or df.empty:
        return
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        key=key or f"dl_{filename}",
    )
