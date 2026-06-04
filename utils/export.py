"""
Relief Docket – export helpers.
"""
import io
import pandas as pd
import streamlit as st


def csv_download_button(
    df: pd.DataFrame,
    filename: str = "relief_docket_export.csv",
    label: str = "⬇ Download CSV",
    key: str = "csv_dl",
) -> None:
    """Render a Streamlit download button for a DataFrame as CSV."""
    if df is None or df.empty:
        return
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button(
        label=label,
        data=buf.getvalue().encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )
