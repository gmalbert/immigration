"""
pages/A_Policy_Appeals.py — Policy Shift Tracker + Appeals Tracker

Tab 1: Policy Shifts — admin closure, terminations, in absentia across administrations
Tab 2: Appeals — BIA volume/outcomes + federal petition trend
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils import add_sidebar, no_data_banner, format_num, format_pct, csv_download_button
from utils.data_loader import (
    load_policy_trends, load_bia_timeline, load_circuit_appeals, get_pipeline_status,
)
from utils.charts import policy_trend_chart, _add_admin_bands
from footer import add_gavel_glimpse_footer

add_sidebar("policy_appeals")

st.title("🏛️ Policy & Appeals")
st.caption(
    "How presidential administrations shape immigration court outcomes — and how cases "
    "move through the two-tier appellate system (BIA → federal circuit courts)."
)

status = get_pipeline_status()
if status.get("seed_mode"):
    st.warning(
        "**Seed mode** — statistics sourced from EOIR Yearbooks, TRAC Immigration, "
        "and Administrative Office of US Courts data.",
        icon="⚠️",
    )

# ── Load all data up-front ────────────────────────────────────────────────────
pol_df  = load_policy_trends()
bia_df  = load_bia_timeline()
circ_df = load_circuit_appeals()

# ── Top-level tabs ────────────────────────────────────────────────────────────
tab_policy, tab_appeals = st.tabs(["🏛️ Policy Shifts", "⚖️ Appeals"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: POLICY SHIFTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_policy:
    st.subheader("Policy Shift Tracker")
    st.markdown(
        "Key immigration court metrics tracked across presidential administrations. "
        "Administration shading shows how policy changes appear in the raw data."
    )

    if pol_df is None or pol_df.empty:
        no_data_banner()
    else:
        admin_closure_available = (
            "admin_closure_rate" in pol_df.columns
            and pol_df["admin_closure_rate"].fillna(0).max() > 0
        )
        if admin_closure_available:
            st.info(
                "**Note on administrative closure:** The code didn't change — the policy behind it did. "
                "Obama used it broadly; Trump I nearly eliminated it; Biden partially restored it; "
                "Trump II has restricted it again.",
                icon="ℹ️",
            )
        else:
            st.info(
                "**Administrative closure is not charted from this EOIR build.** "
                "The current CASE proceeding outcome fields do not expose a usable administrative-closure "
                "trend, so the dashboard does not draw a flat zero line. Terminations and in absentia "
                "rates below are real EOIR-derived policy-sensitive measures.",
                icon="ℹ️",
            )

        year_range = st.slider(
            "Fiscal Year Range",
            min_value=int(pol_df["fiscal_year"].min()),
            max_value=int(pol_df["fiscal_year"].max()),
            value=(2000, int(pol_df["fiscal_year"].max())),
            key="pol_year_range",
        )
        chart_df = pol_df[pol_df["fiscal_year"].between(year_range[0], year_range[1])].copy()

        ptab1, ptab2, ptab3, ptab4 = st.tabs([
            "Admin Closure", "Terminations", "In Absentia", "All Metrics"
        ])

        with ptab1:
            st.markdown(
                "**Administrative closure** temporarily suspends a case without dismissal. "
                "Use varied dramatically by administration."
            )
            if admin_closure_available:
                fig = policy_trend_chart(chart_df, "admin_closure_rate",
                    "Administrative Closure Rate - Share of Completed Cases Administratively Closed")
                if fig:
                    st.plotly_chart(fig, width='stretch')
            else:
                st.warning(
                    "No administrative-closure outcome signal is populated in the current real-data "
                    "policy aggregate. This is a data limitation, not evidence that administrative "
                    "closure never occurred.",
                    icon="⚠️",
                )
            with st.expander("Policy context"):
                st.markdown("""
| Period | Policy | Effect on data |
|---|---|---|
| Pre-2010 | Rarely used | Low but non-zero rates |
| Obama 2011–2014 | Morton Memo prosecutorial discretion; DACA priorities | Rate rises into the mid-2010s |
| Trump I 2017 | AG Sessions restricts IJ authority to close cases | Policy context changes the interpretation of later years |
| Biden 2021 | AG Garland restores IJ authority | Administrative closure becomes available again |
| Trump II 2025 | Further restrictions | Renewed decline in current-release data |
                """)

        with ptab2:
            st.markdown(
                "**Terminations** end proceedings entirely (e.g., DHS withdraws charges). "
                "Distinct from dismissals and administrative closure."
            )
            fig = policy_trend_chart(chart_df, "termination_rate",
                "Termination Rate — Share of Cases Terminated")
            if fig:
                st.plotly_chart(fig, width='stretch')

        with ptab3:
            st.markdown(
                "**In absentia orders** are issued when a respondent fails to appear for their hearing."
            )
            fig = policy_trend_chart(chart_df, "in_absentia_rate",
                "In Absentia Rate — Share of Cases Decided in Respondent's Absence")
            if fig:
                st.plotly_chart(fig, width='stretch')
            with st.expander("Context on in absentia rates"):
                st.markdown("""
- **Address accuracy issues:** Respondents who move without updating may not receive hearing notices
- **NTA defects:** Notices without specific dates ("time and date TBD") create confusion
- **Enforcement priorities:** Higher enforcement can incentivize non-appearance
- **Representation:** Unrepresented respondents miss hearings at higher rates

In absentia orders can be reopened if the respondent can demonstrate they did not receive adequate notice.
                """)

        with ptab4:
            st.markdown("### All Policy Metrics by Year")
            display_df = chart_df.copy()
            for col in ["admin_closure_rate", "termination_rate", "in_absentia_rate"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda v: f"{v*100:.1f}%")
            if "total_completions" in display_df.columns:
                display_df["total_completions"] = display_df["total_completions"].apply(
                    lambda v: f"{int(v):,}")
            st.dataframe(
                display_df.sort_values("fiscal_year", ascending=False).rename(columns={
                    "fiscal_year": "Fiscal Year",
                    "total_completions": "Total Completions",
                    "admin_closure_rate": "Admin Closure Rate",
                    "termination_rate": "Termination Rate",
                    "in_absentia_rate": "In Absentia Rate",
                }),
                width='stretch',
                hide_index=True,
                height=500,
            )
            csv_download_button(pol_df, "relief_docket_policy_trends.csv",
                                key="pol_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: APPEALS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_appeals:
    C_RECEIPTS = "#2980b9"
    C_DISMISS  = "#c0392b"
    C_SUSTAIN  = "#1e8a50"
    C_REMAND   = "#e67e22"
    C_DHS      = "#8e44ad"
    C_PENDING  = "#7f8c8d"

    st.subheader("Immigration Appeals Tracker")
    st.caption(
        "Board of Immigration Appeals (BIA) case volumes and outcomes, plus federal circuit "
        "court petitions for review."
    )

    if bia_df is None or bia_df.empty:
        st.info("BIA appeal timeline data is not available in the current real-data build.")
    else:
        min_yr, max_yr = int(bia_df["fiscal_year"].min()), int(bia_df["fiscal_year"].max())
        app_yr = st.slider("Fiscal year range", min_value=min_yr, max_value=max_yr,
                           value=(2005, max_yr), step=1, key="app_yr_range")
        df = bia_df[(bia_df["fiscal_year"] >= app_yr[0]) & (bia_df["fiscal_year"] <= app_yr[1])].copy()

        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) > 1 else latest
        reversal_rate = (latest["sustained"] + latest["remanded"]) / latest["completions"] if latest["completions"] else 0
        prev_rev_rate = (prev["sustained"] + prev["remanded"]) / prev["completions"] if prev["completions"] else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"BIA Receipts ({int(latest['fiscal_year'])})",
                    format_num(latest["receipts"]),
                    delta=f"{int(latest['receipts'] - prev['receipts']):+,}", delta_color="off")
        col2.metric("Pending Backlog", format_num(latest["pending"]),
                    delta=f"{int(latest['pending'] - prev['pending']):+,}", delta_color="inverse")
        col3.metric("Non-Affirmance Rate", format_pct(reversal_rate),
                    delta=f"{(reversal_rate - prev_rev_rate)*100:+.1f}pp", delta_color="off")
        if circ_df is not None and not circ_df.empty:
            fed_df = circ_df.dropna(subset=["fiscal_year"]).sort_values("fiscal_year")
            fed_latest = fed_df.iloc[-1] if not fed_df.empty else None
            col4.metric("Federal Remand Rate",
                        format_pct(fed_latest["reversal_rate"] if fed_latest is not None else circ_df["reversal_rate"].mean()))
        else:
            col4.metric("Federal Data", "—")

        atab1, atab2, atab3 = st.tabs(["📈 BIA Volume & Backlog",
                                        "📊 BIA Outcome Breakdown",
                                        "🏛️ Federal Courts"])

        with atab1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["fiscal_year"], y=df["pending"],
                name="Pending (right axis)",
                fill="tozeroy", fillcolor="rgba(127,140,141,0.18)",
                line=dict(color=C_PENDING, width=1.5, dash="dot"),
                yaxis="y2",
                hovertemplate="FY%{x} — Pending: %{y:,.0f}<extra></extra>",
            ))
            fig.add_trace(go.Bar(x=df["fiscal_year"], y=df["receipts"],
                name="Receipts", marker_color=C_RECEIPTS, opacity=0.85,
                hovertemplate="FY%{x} — Receipts: %{y:,.0f}<extra></extra>"))
            fig.add_trace(go.Bar(x=df["fiscal_year"], y=df["completions"],
                name="Completions", marker_color="#1abc9c", opacity=0.8,
                hovertemplate="FY%{x} — Completions: %{y:,.0f}<extra></extra>"))
            fig.update_layout(
                barmode="group",
                yaxis=dict(title="Appeals (cases)", tickformat=","),
                yaxis2=dict(title="Pending Backlog", tickformat=",",
                            overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified", margin=dict(t=60, b=40), height=440,
            )
            fig = _add_admin_bands(fig)
            st.plotly_chart(fig, width="stretch")
            csv_download_button(bia_df, "relief_docket_bia_timeline.csv",
                                key="app_bia_dl")

        with atab2:
            outcome_series = [
                ("dismissed", "Dismissed / Denied / Affirmed", C_DISMISS),
                ("remanded",  "Remanded to IJ",          C_REMAND),
                ("sustained", "Sustained / Granted",     C_SUSTAIN),
                ("dhs_appeals","DHS / INS Appeals",      C_DHS),
            ]
            outcome_cols = [col for col, _, _ in outcome_series]
            outcome_df = df[["fiscal_year", "completions", *outcome_cols]].copy()
            outcome_df[outcome_cols] = outcome_df[outcome_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            if outcome_df[outcome_cols].sum().sum() == 0:
                st.warning(
                    "BIA outcome categories are present but all values are zero in the loaded data. "
                    "Refresh Streamlit or rebuild `data/bia_timeline.parquet` if this persists."
                )
            else:
                fig2 = go.Figure()
                for y_col, name, color in outcome_series:
                    fig2.add_trace(go.Bar(x=outcome_df["fiscal_year"], y=outcome_df[y_col],
                        name=name, marker_color=color,
                        hovertemplate=f"FY%{{x}} — {name}: %{{y:,.0f}}<extra></extra>"))
                fig2.update_layout(barmode="stack",
                    yaxis=dict(title="Cases", tickformat=","),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    hovermode="x unified", margin=dict(t=60, b=40), height=440)
                fig2 = _add_admin_bands(fig2)
                st.plotly_chart(fig2, width="stretch")

            df_nr = df.copy()
            df_nr["non_affirm_rate"] = (df_nr["sustained"] + df_nr["remanded"]) / df_nr["completions"]
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=df_nr["fiscal_year"], y=df_nr["non_affirm_rate"],
                mode="lines+markers", name="Non-Affirmance Rate",
                line=dict(color=C_SUSTAIN, width=2.5),
                fill="tozeroy", fillcolor="rgba(30,138,80,0.12)",
                hovertemplate="FY%{x} — Non-Affirmance: %{y:.1%}<extra></extra>"))
            fig3.update_layout(yaxis=dict(title="Share of Completions", tickformat=".0%"),
                               margin=dict(t=30, b=40), height=250)
            fig3 = _add_admin_bands(fig3)
            st.plotly_chart(fig3, width="stretch")

            table_df = outcome_df.sort_values("fiscal_year", ascending=False).rename(columns={
                "fiscal_year": "Fiscal Year",
                "completions": "Completions",
                "dismissed": "Dismissed / Denied / Affirmed",
                "remanded": "Remanded",
                "sustained": "Sustained / Granted",
                "dhs_appeals": "DHS / INS Appeals",
            })
            st.dataframe(table_df, width="stretch", hide_index=True, height=320)

            with st.expander("BIA streamlining — what happened in 2002?"):
                st.markdown("""
In 2002, AG John Ashcroft allowed the BIA to issue **affirmances without opinion (AWO)**
and use **single-member panels**, reducing BIA from 23 to 11 members. The backlog cleared
rapidly but critics argue review quality deteriorated. This shift drove a spike in petitions
for review in the federal circuit courts after 2003.
                """)

        with atab3:
            if circ_df is None or circ_df.empty:
                st.info("Federal court appeal data not available.")
            else:
                fed_df = circ_df.dropna(subset=["fiscal_year"]).sort_values("fiscal_year").copy()
                fed_df = fed_df[(fed_df["fiscal_year"] >= app_yr[0]) & (fed_df["fiscal_year"] <= app_yr[1])]

                st.caption(
                    "EOIR exposes federal petition-for-review records and coded federal remands, "
                    "but this table does not expose circuit identity. This is an annual federal trend, "
                    "not a circuit-by-circuit comparison."
                )

                fig4 = go.Figure()
                fig4.add_trace(go.Bar(
                    x=fed_df["fiscal_year"], y=fed_df["petitions_filed"],
                    name="Petitions Filed",
                    marker_color=C_RECEIPTS,
                    hovertemplate="FY%{x} — Petitions: %{y:,.0f}<extra></extra>",
                ))
                fig4.add_trace(go.Scatter(
                    x=fed_df["fiscal_year"], y=fed_df["granted_remanded"],
                    mode="lines+markers",
                    name="Recorded Remands",
                    line=dict(color=C_REMAND, width=2.5),
                    yaxis="y2",
                    hovertemplate="FY%{x} — Remands: %{y:,.0f}<extra></extra>",
                ))
                fig4.update_layout(
                    yaxis=dict(title="Petitions Filed", tickformat=","),
                    yaxis2=dict(title="Recorded Remands", tickformat=",",
                                overlaying="y", side="right", showgrid=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    hovermode="x unified",
                    height=420,
                    margin=dict(t=60, b=40),
                )
                fig4 = _add_admin_bands(fig4)
                st.plotly_chart(fig4, width="stretch")

                fig5 = go.Figure()
                fig5.add_trace(go.Scatter(
                    x=fed_df["fiscal_year"], y=fed_df["reversal_rate"],
                    mode="lines+markers",
                    name="Recorded Federal Remand Rate",
                    line=dict(color=C_SUSTAIN, width=2.5),
                    fill="tozeroy",
                    fillcolor="rgba(30,138,80,0.12)",
                    hovertemplate="FY%{x} — Remand rate: %{y:.1%}<extra></extra>",
                ))
                fig5.update_layout(
                    yaxis=dict(title="Share of Petitions", tickformat=".1%"),
                    margin=dict(t=30, b=40),
                    height=300,
                )
                fig5 = _add_admin_bands(fig5)
                st.plotly_chart(fig5, width="stretch")

                tbl = fed_df.copy()
                tbl["reversal_rate"] = tbl["reversal_rate"].map("{:.1%}".format)
                tbl["petitions_filed"] = tbl["petitions_filed"].map("{:,}".format)
                tbl["granted_remanded"] = tbl["granted_remanded"].map("{:,}".format)
                if "median_days" in tbl.columns:
                    tbl["median_days"] = tbl["median_days"].round(0).astype("Int64").astype(str)
                from utils import clean_dataframe_columns
                st.dataframe(clean_dataframe_columns(tbl), width="stretch", hide_index=True)
                csv_download_button(circ_df, "relief_docket_circuit_appeals.csv",
                                    key="app_circ_dl")

add_gavel_glimpse_footer()
