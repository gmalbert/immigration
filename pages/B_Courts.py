"""
pages/B_Courts.py — Courts & Geography (merged)

Tab 1: Court Profiles — caseloads, grant rates, representation rates by court
Tab 2: Geographic View — US court bubble map, world origin choropleth, circuit bar
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils import add_sidebar, no_data_banner, format_num, format_pct, csv_download_button
from utils.data_loader import load_court_metrics, load_nationality_metrics, has_any_data
from utils.charts import court_comparison_chart
from footer import add_gavel_glimpse_footer

add_sidebar("courts")

st.title("🏛️ Courts & Geography")
st.caption(
    "Immigration court profiles, geographic caseload distribution, and "
    "circuit-level comparison."
)

court_df = load_court_metrics()
nat_df   = load_nationality_metrics()

tab_courts, tab_geo = st.tabs(["🏛️ Court Profiles", "🗺️ Geographic View"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: COURT PROFILES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_courts:
    st.subheader("Immigration Court Profiles")
    st.markdown(
        "Caseloads, asylum grant rates, representation rates, and backlogs "
        "for the 70+ U.S. immigration courts."
    )

    if court_df is None or court_df.empty:
        no_data_banner()
    else:
        total_courts  = len(court_df)
        total_pending = court_df.get("pending_cases", pd.Series(dtype=int)).sum()
        median_grant  = court_df["asylum_grant_rate"].median()

        col1, col2, col3 = st.columns(3)
        col1.metric("Courts in Dataset",    format_num(total_courts))
        col2.metric("Total Pending Cases",  format_num(total_pending))
        col3.metric("Median Grant Rate",    format_pct(median_grant))

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            if "circuit" in court_df.columns:
                circuits = ["All"] + sorted(court_df["circuit"].dropna().unique())
                circuit_filter = st.selectbox("Circuit", circuits, key="court_circuit")
            else:
                circuit_filter = "All"
        with col_f2:
            metric_options = {
                "Asylum Grant Rate": "asylum_grant_rate",
                "Representation Rate": "representation_rate",
                "Total Cases": "total_cases",
                "Pending Cases": "pending_cases",
            }
            metric_label = st.selectbox("Compare by", list(metric_options.keys()),
                                         key="court_metric")
        metric_col = metric_options[metric_label]
        filtered = court_df.copy()
        if circuit_filter != "All" and "circuit" in court_df.columns:
            filtered = filtered[filtered["circuit"] == circuit_filter]

        fig = court_comparison_chart(filtered, metric_col=metric_col,
                                      title=f"{metric_label} by Court")
        if fig:
            st.plotly_chart(fig, width='stretch')

        ctab1, ctab2 = st.tabs(["📋 All Courts", "🗺️ Northeast Spotlight"])
        with ctab1:
            display_cols = [c for c in [
                "court_city", "state", "circuit", "total_cases", "pending_cases",
                "asylum_grant_rate", "representation_rate",
            ] if c in filtered.columns]
            display_df = filtered[display_cols].sort_values(
                metric_col if metric_col in display_cols else display_cols[0],
                ascending=False,
            ).copy()
            for col in ["asylum_grant_rate", "representation_rate"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda v: f"{v*100:.1f}%")
            for col in ["total_cases", "pending_cases"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(
                        lambda v: f"{int(v):,}" if pd.notna(v) else "—")
            from utils import clean_dataframe_columns
            st.dataframe(clean_dataframe_columns(display_df), width='stretch', height=500, hide_index=True)
            csv_download_button(court_df, "relief_docket_courts.csv", key="court_dl")

        with ctab2:
            st.markdown("""
### Northeast / First Circuit Spotlight

The **Boston Immigration Court** handles cases from Massachusetts, New Hampshire,
Maine, and Rhode Island. The First Circuit courts tend to have higher representation
rates and grant rates than the national average.
            """)
            ne_df = pd.DataFrame()
            if "court_code" in court_df.columns:
                ne_df = court_df[court_df["court_code"].isin(["BOS", "PRO", "PHL", "HAR"])].copy()
            elif "state" in court_df.columns:
                ne_df = court_df[court_df["state"].isin(
                    ["MA", "NH", "ME", "RI", "CT", "VT"])].copy()
            if ne_df.empty:
                st.info("Northeast court data not available in current dataset.")
            else:
                cols_to_show = [c for c in ["court_city", "state", "total_cases",
                    "pending_cases", "asylum_grant_rate", "representation_rate"]
                    if c in ne_df.columns]
                display_ne = ne_df[cols_to_show].copy()
                for col in ["asylum_grant_rate", "representation_rate"]:
                    if col in display_ne.columns:
                        display_ne[col] = display_ne[col].apply(lambda v: f"{v*100:.1f}%")
                from utils import clean_dataframe_columns
                st.dataframe(clean_dataframe_columns(display_ne), width='stretch', hide_index=True)
                ne_fig = court_comparison_chart(ne_df, metric_col="asylum_grant_rate",
                    title="Asylum Grant Rate — Northeast Courts")
                if ne_fig:
                    st.plotly_chart(ne_fig, width='stretch')

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: GEOGRAPHIC VIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab_geo:
    COURT_COORDS = {
        "NYC": (40.71, -74.00), "LAX": (34.05, -118.24), "HOU": (29.76, -95.37),
        "SFR": (37.77, -122.42), "CHI": (41.88, -87.63), "MIA": (25.77, -80.19),
        "DAL": (32.78, -96.80), "DEN": (39.74, -104.98), "ATL": (33.75, -84.39),
        "PHI": (39.95, -75.17), "BAL": (39.29, -76.61), "BOS": (42.36, -71.06),
        "SAN": (29.42, -98.49), "ELP": (31.76, -106.49), "SLD": (32.72, -117.16),
        "POR": (45.52, -122.68), "SEA": (47.61, -122.33), "MNP": (44.98, -93.27),
        "DET": (42.33, -83.05), "CLE": (41.50, -81.69), "HAR": (41.76, -72.68),
        "PRO": (41.82, -71.42), "PHL": (43.66, -70.26), "NOR": (29.95, -90.07),
        "LOU": (38.25, -85.76), "PHX": (33.45, -112.07), "TUC": (32.22, -110.97),
        "COR": (35.23, -80.84),
    }
    EOIR_TO_ISO3 = {
        "MEX": "MEX", "GTM": "GTM", "HND": "HND", "SLV": "SLV", "VEN": "VEN",
        "CUB": "CUB", "CHN": "CHN", "IND": "IND", "ECU": "ECU", "COL": "COL",
        "NIC": "NIC", "HAI": "HTI", "ETH": "ETH", "ERI": "ERI", "SOM": "SOM",
        "COD": "COD", "AFG": "AFG", "IRQ": "IRQ", "SYR": "SYR", "IRN": "IRN",
        "CAN": "CAN", "PHL": "PHL", "BRA": "BRA", "JAM": "JAM", "PER": "PER",
        "NGA": "NGA", "PAK": "PAK", "GHA": "GHA", "BGR": "BGR", "ALB": "ALB",
        "ARM": "ARM", "GEO": "GEO", "RUS": "RUS", "UKR": "UKR", "DOM": "DOM",
        "HTI": "HTI", "KGZ": "KGZ", "UZB": "UZB", "TUR": "TUR", "CMR": "CMR",
        "SEN": "SEN", "CIV": "CIV", "BOL": "BOL", "ARG": "ARG", "CRI": "CRI",
    }

    g1, g2, g3 = st.tabs(["🏛️ US Courts Map", "🌍 Origin Countries", "⚡ Circuit Comparison"])

    with g1:
        if court_df is None or court_df.empty:
            st.info("Court data not available.")
        else:
            cdf = court_df.copy()
            cdf["lat"] = cdf["court_code"].map(lambda c: COURT_COORDS.get(c, (None, None))[0])
            cdf["lon"] = cdf["court_code"].map(lambda c: COURT_COORDS.get(c, (None, None))[1])
            cdf["grant_pct"] = (cdf["asylum_grant_rate"] * 100).round(1)
            cdf["rep_pct"]   = (cdf["representation_rate"] * 100).round(1)
            cdf["label"]     = cdf["court_city"] + " (" + cdf["court_code"] + ")"
            cdf = cdf.dropna(subset=["lat", "lon"])

            color_by = st.radio(
                "Color courts by",
                ["Asylum Grant Rate", "Representation Rate", "Pending Caseload"],
                horizontal=True, key="court_map_color",
            )
            color_col = {"Asylum Grant Rate": "grant_pct",
                         "Representation Rate": "rep_pct",
                         "Pending Caseload": "pending_cases"}[color_by]

            fig = px.scatter_geo(
                cdf, lat="lat", lon="lon",
                size="pending_cases", color=color_col,
                hover_name="label",
                hover_data={"grant_pct": ":.1f", "rep_pct": ":.1f",
                            "pending_cases": ":,", "total_cases": ":,",
                            "circuit": True, "lat": False, "lon": False},
                color_continuous_scale="RdYlGn",
                labels={"grant_pct": "Grant Rate (%)", "rep_pct": "Represented (%)",
                        "pending_cases": "Pending Cases"},
                scope="usa", size_max=55,
            )
            fig.update_layout(height=560, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, width='stretch')

            with st.expander("Court data table"):
                show = cdf[["label", "circuit", "total_cases", "pending_cases",
                             "grant_pct", "rep_pct"]].copy()
                show.columns = ["Court", "Circuit", "Total Cases", "Pending",
                                 "Grant Rate %", "Represented %"]
                st.dataframe(show.sort_values("Pending", ascending=False),
                             width='stretch', hide_index=True)

    with g2:
        if nat_df is None or nat_df.empty:
            st.info("Nationality data not available.")
        else:
            ndf = nat_df.copy()
            ndf["iso3"]      = ndf["nat_code"].map(EOIR_TO_ISO3)
            ndf["grant_pct"] = (ndf["asylum_grant_rate"] * 100).round(1)
            ndf["rep_pct"]   = (ndf["representation_rate"] * 100).round(1)
            ndf = ndf.dropna(subset=["iso3"])

            world_color = st.radio(
                "Color countries by",
                ["Case Volume", "Asylum Grant Rate"],
                horizontal=True, key="world_map_color",
            )
            if world_color == "Case Volume":
                color_col2, title2, scale2 = "case_count", "Country of Origin — Total Cases", "Blues"
            else:
                color_col2, title2, scale2 = "grant_pct", "Country of Origin — Asylum Grant Rate (%)", "RdYlGn"

            fig2 = px.choropleth(
                ndf, locations="iso3", color=color_col2,
                hover_name="nat_code",
                hover_data={"grant_pct": ":.1f", "case_count": ":,", "iso3": False},
                color_continuous_scale=scale2,
                labels={"grant_pct": "Grant Rate (%)", "case_count": "Total Cases"},
                title=title2,
            )
            fig2.update_layout(height=520, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig2, width='stretch')

            csv_download_button(nat_df, "relief_docket_nationalities_geo.csv",
                                key="geo_nat_dl")

    with g3:
        if court_df is None or court_df.empty:
            st.info("Court data not available.")
        else:
            if "circuit" in court_df.columns:
                circ_grp = (
                    court_df.groupby("circuit")
                    .agg(grant_pct=("asylum_grant_rate", "mean"),
                         rep_pct=("representation_rate", "mean"),
                         n=("court_city", "count"))
                    .reset_index()
                    .sort_values("grant_pct", ascending=False)
                )
                circ_grp["grant_pct"] = (circ_grp["grant_pct"] * 100).round(1)
                circ_grp["rep_pct"]   = (circ_grp["rep_pct"]   * 100).round(1)

                fig3 = go.Figure()
                fig3.add_trace(go.Bar(
                    x=circ_grp["circuit"], y=circ_grp["grant_pct"],
                    name="Avg Grant Rate %", marker_color="#1e8a50",
                    hovertemplate="%{x}: %{y:.1f}% grant<extra></extra>",
                ))
                fig3.add_trace(go.Bar(
                    x=circ_grp["circuit"], y=circ_grp["rep_pct"],
                    name="Avg Represented %", marker_color="#2980b9",
                    hovertemplate="%{x}: %{y:.1f}% represented<extra></extra>",
                ))
                fig3.update_layout(
                    barmode="group",
                    yaxis=dict(title="Rate (%)", ticksuffix="%"),
                    legend=dict(orientation="h", y=1.1),
                    height=400,
                    margin=dict(t=20, b=40),
                )
                st.plotly_chart(fig3, width='stretch')
                st.caption("Each circuit bar = average across all courts in that circuit.")
            else:
                st.info("Circuit data not available in current dataset.")

            csv_download_button(court_df, "relief_docket_courts_geo.csv",
                                key="geo_court_dl")

add_gavel_glimpse_footer()
