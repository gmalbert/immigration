"""
pages/C_Case_Processing.py — Case Processing (merged)

Tab 1: Case Outcomes — removal, grant, voluntary departure, admin closure by year
Tab 2: Backlog — pending caseload growth and projections
Tab 3: Case Age — how long cases take by court, detention status, and representation
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

from utils import add_sidebar, no_data_banner, format_num, format_pct, csv_download_button
from utils.data_loader import (
    load_case_outcomes, load_case_outcomes_annual, load_backlog_timeline,
    load_case_age_timeline, load_case_age_by_court, load_backlog_age_dist,
    get_pipeline_status,
)
from utils.charts import (
    outcome_trend_chart, backlog_timeline_chart, _add_admin_bands,
)
from footer import add_gavel_glimpse_footer

add_sidebar("case_processing")

st.title("📊 Case Processing")
st.caption(
    "How immigration cases resolve — outcomes, backlog growth, and processing time "
    "broken down by year, court, and detention status."
)

status = get_pipeline_status()
if status.get("seed_mode"):
    st.warning(
        "**Seed mode** — statistics sourced from EOIR Yearbooks, TRAC Immigration, "
        "Vera Institute, and GAO reports.",
        icon="⚠️",
    )

# Load all data
outcomes_df  = load_case_outcomes()
outcomes_annual_df = load_case_outcomes_annual()
backlog_df   = load_backlog_timeline()
age_df       = load_case_age_timeline()
court_age_df = load_case_age_by_court()
age_dist_df  = load_backlog_age_dist()

tab_out, tab_backlog, tab_age = st.tabs(["📋 Case Outcomes", "📈 Backlog", "⏳ Case Age & Wait Times"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: CASE OUTCOMES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_out:
    st.subheader("Case Outcomes")
    st.markdown(
        "How immigration court cases resolve — removals, asylum grants, "
        "voluntary departure, administrative closure, and more."
    )
    st.info(
        "**Scope note:** This data covers cases adjudicated by immigration judges (EOIR). "
        "Expedited removal by DHS/ICE is not included.",
        icon="ℹ️",
    )
    if outcomes_df is None or outcomes_df.empty:
        no_data_banner()
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            years = sorted(outcomes_df["fiscal_year"].dropna().unique().astype(int))
            year_range = st.slider("Fiscal Year Range",
                min_value=int(min(years)), max_value=int(max(years)),
                value=(2000, int(max(years))), key="out_year_range")
        with col_f2:
            all_outcomes = sorted(outcomes_df["outcome_type"].dropna().unique())
            selected_outcomes = st.multiselect("Outcome Types",
                options=all_outcomes, default=all_outcomes, key="out_outcomes")

        filt = outcomes_df[
            outcomes_df["fiscal_year"].between(year_range[0], year_range[1]) &
            outcomes_df["outcome_type"].isin(selected_outcomes)
        ].copy()

        fig = outcome_trend_chart(filt)
        if fig:
            st.plotly_chart(fig, width='stretch')

        st.markdown("### Annual Summary")
        if outcomes_annual_df is not None and not outcomes_annual_df.empty:
            summary_cols = ["fiscal_year", *selected_outcomes]
            summary_cols = [c for c in summary_cols if c in outcomes_annual_df.columns]
            pivot = outcomes_annual_df[
                outcomes_annual_df["fiscal_year"].between(year_range[0], year_range[1])
            ][summary_cols].copy()
            outcome_cols = [c for c in pivot.columns if c != "fiscal_year"]
            pivot["Total"] = pivot[outcome_cols].sum(axis=1)
            pivot = pivot.sort_values("fiscal_year", ascending=False)
        else:
            pivot = (
                filt.pivot_table(index="fiscal_year", columns="outcome_type",
                                 values="case_count", aggfunc="sum", fill_value=0)
                .reset_index()
                .sort_values("fiscal_year", ascending=False)
            )
            pivot.columns.name = None
            pivot["Total"] = pivot.select_dtypes("number").drop(columns=["fiscal_year"], errors="ignore").sum(axis=1)
        from utils import clean_dataframe_columns
        st.dataframe(clean_dataframe_columns(pivot.set_index("fiscal_year")), width='stretch', height=400)

        with st.expander("Understanding outcome codes"):
            st.markdown("""
| Outcome | Meaning |
|---|---|
| **Removed** | Immigration judge ordered respondent removed (deported) |
| **Granted** | Relief was granted (asylum, withholding, cancellation, etc.) |
| **Voluntary Departure** | Respondent allowed to leave voluntarily |
| **Admin Closed** | Case placed on hold; usage varies by administration |
| **Dismissed** | Proceedings terminated without an order |
| **In Absentia** | Respondent failed to appear; removal order issued |
| **Terminated** | Proceedings ended (e.g., DHS withdrew charges) |
            """)

        csv_download_button(filt, "relief_docket_case_outcomes.csv", key="out_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: BACKLOG
# ═══════════════════════════════════════════════════════════════════════════════
with tab_backlog:
    st.subheader("Backlog Tracker")
    st.markdown(
        "The U.S. immigration court backlog grew from ~300,000 pending cases in 2010 "
        "to **over 3.3 million** as of early 2026."
    )
    if backlog_df is None or backlog_df.empty:
        no_data_banner()
    else:
        bl_sorted = backlog_df.sort_values("fiscal_year")
        latest_bl = bl_sorted.iloc[-1]
        prev_bl   = bl_sorted.iloc[-2] if len(bl_sorted) > 1 else latest_bl

        col1, col2, col3 = st.columns(3)
        col1.metric(
            f"Pending Cases (FY{int(latest_bl['fiscal_year'])})",
            format_num(latest_bl["pending_cases"]),
            delta=format_num(latest_bl["pending_cases"] - prev_bl["pending_cases"]),
            delta_color="inverse",
        )
        oldest_bl = bl_sorted.iloc[0]
        growth = (latest_bl["pending_cases"] / oldest_bl["pending_cases"] - 1) * 100 if oldest_bl["pending_cases"] else 0
        col2.metric(f"Growth since FY{int(oldest_bl['fiscal_year'])}", f"+{growth:.0f}%")
        peak_bl = backlog_df.loc[backlog_df["pending_cases"].idxmax()]
        col3.metric("Peak Year", f"FY{int(peak_bl['fiscal_year'])}",
                    format_num(peak_bl["pending_cases"]))

        bl_min = int(backlog_df["fiscal_year"].min())
        bl_max = int(backlog_df["fiscal_year"].max())
        if bl_min == bl_max:
            bl_yr = (bl_min, bl_max)
            st.caption(f"Backlog snapshot available for FY{bl_max}.")
        else:
            bl_yr = st.slider(
                "Fiscal Year Range",
                min_value=bl_min,
                max_value=bl_max,
                value=(max(1998, bl_min), bl_max),
                key="backlog_years",
            )
        chart_bl = backlog_df[backlog_df["fiscal_year"].between(bl_yr[0], bl_yr[1])].copy()
        fig_bl = backlog_timeline_chart(chart_bl)
        if fig_bl:
            st.plotly_chart(fig_bl, width='stretch')

        st.markdown("### Backlog Growth by Presidential Administration")
        admin_periods = [
            ("Clinton",  1997, 2001), ("Bush",   2001, 2009),
            ("Obama",    2009, 2017), ("Trump I", 2017, 2021),
            ("Biden",    2021, 2025), ("Trump II", 2025, 2026),
        ]
        admin_rows = []
        for admin, start, end in admin_periods:
            p = backlog_df[backlog_df["fiscal_year"].between(start, end - 1)]
            if p.empty:
                continue
            s, e = p["pending_cases"].iloc[0], p["pending_cases"].iloc[-1]
            chg = e - s
            pct = (chg / s * 100) if s else 0
            admin_rows.append({"Administration": admin, "Period": f"FY{start}–FY{end-1}",
                "Start Pending": format_num(s), "End Pending": format_num(e),
                "Change": f"{'+' if chg >= 0 else ''}{format_num(chg)}",
                "% Change": f"{'+' if pct >= 0 else ''}{pct:.0f}%"})
        if admin_rows:
            from utils import clean_dataframe_columns
            st.dataframe(clean_dataframe_columns(pd.DataFrame(admin_rows)), width='stretch', hide_index=True)

        with st.expander("What drives the backlog?"):
            st.markdown("""
1. **Funding vs. filings gap** — Congress has not funded courts at a rate matching NTA growth
2. **NTA surge periods** — Large waves add cases without immediate resolution capacity
3. **Policy-driven continuances** — Administrative closure removal re-docketed millions of cases
4. **Judicial vacancies** — IJs hired by DOJ; slowdowns directly reduce adjudication capacity
5. **COVID-19** — Courts paused in 2020; gap in completions while filings continued
6. **MPP wind-down** — Biden ended Remain in Mexico; thousands re-docketed in US courts
            """)

        csv_download_button(backlog_df, "relief_docket_backlog.csv", key="backlog_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: CASE AGE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_age:
    st.subheader("Case Age & Wait Time Tracker")
    st.caption(
        "Median days from Notice to Appear (NTA) to final order, broken down by "
        "year, court, detention status, and representation."
    )

    if age_df is None or age_df.empty:
        no_data_banner()
    else:
        min_yr_a = int(age_df["fiscal_year"].min())
        max_yr_a = int(age_df["fiscal_year"].max())
        age_yr = st.slider("Fiscal year range",
            min_value=min_yr_a, max_value=max_yr_a,
            value=(max(2005, min_yr_a), max_yr_a), key="age_yr_range")
        age_f = age_df[(age_df["fiscal_year"] >= age_yr[0]) & (age_df["fiscal_year"] <= age_yr[1])].copy()

        la = age_f.iloc[-1]
        pr = age_f.iloc[-2] if len(age_f) > 1 else la
        ratio = la["prose_median"] / la["represented_median"] if la["represented_median"] else 1

        def fmt_days(days: float) -> str:
            return f"{days / 365:.1f} yrs ({int(days):,}d)"

        median_delta = int(la["median_days"] - pr["median_days"])
        delta_class = "bad" if median_delta > 0 else "good" if median_delta < 0 else "neutral"
        st.markdown(f"""
        <style>
        .case-age-metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 0.75rem;
            margin: 0.25rem 0 1.25rem;
        }}
        .case-age-card {{
            border: 1px solid rgba(49, 51, 63, 0.18);
            border-radius: 8px;
            padding: 0.75rem 0.85rem;
            background: #fff;
            min-width: 0;
        }}
        .case-age-label {{
            color: #555;
            font-size: 0.82rem;
            line-height: 1.15;
            margin-bottom: 0.4rem;
        }}
        .case-age-value {{
            color: #111;
            font-size: clamp(1.05rem, 3.5vw, 1.45rem);
            font-weight: 700;
            line-height: 1.15;
            overflow-wrap: anywhere;
        }}
        .case-age-delta {{
            font-size: 0.88rem;
            line-height: 1.2;
            margin-top: 0.35rem;
        }}
        .case-age-delta.bad {{ color: #c0392b; }}
        .case-age-delta.good {{ color: #1e8a50; }}
        .case-age-delta.neutral {{ color: #666; }}
        </style>
        <div class="case-age-metrics">
            <div class="case-age-card">
                <div class="case-age-label">Median Case Length (FY{int(la['fiscal_year'])})</div>
                <div class="case-age-value">{fmt_days(la['median_days'])}</div>
                <div class="case-age-delta {delta_class}">{median_delta:+,}d</div>
            </div>
            <div class="case-age-card">
                <div class="case-age-label">Non-Detained Median</div>
                <div class="case-age-value">{fmt_days(la['nondetained_median'])}</div>
            </div>
            <div class="case-age-card">
                <div class="case-age-label">Detained Median</div>
                <div class="case-age-value">{fmt_days(la['detained_median'])}</div>
            </div>
            <div class="case-age-card">
                <div class="case-age-label">Pro Se vs. Represented Ratio</div>
                <div class="case-age-value">{ratio:.1f}×</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        at1, at2, at3, at4 = st.tabs([
            "📈 National Trend", "⚖️ Detained vs Non-Detained",
            "🏛️ By Court", "🗂️ Backlog Age"
        ])

        with at1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pd.concat([age_f["fiscal_year"], age_f["fiscal_year"].iloc[::-1]]),
                y=pd.concat([age_f["p75_days"], age_f["p25_days"].iloc[::-1]]),
                fill="toself", fillcolor="rgba(41,128,185,0.12)",
                line=dict(color="rgba(0,0,0,0)"), name="P25–P75 range", hoverinfo="skip"))
            fig.add_trace(go.Scatter(
                x=age_f["fiscal_year"], y=age_f["median_days"],
                mode="lines+markers", name="Median days",
                line=dict(color="#2980b9", width=2.5), marker=dict(size=5),
                hovertemplate="FY%{x} — %{y:,.0f} days (%{customdata:.1f} yrs)<extra></extra>",
                customdata=age_f["median_days"] / 365))
            for y_val, label in [(365, "1 yr"), (730, "2 yrs"), (1095, "3 yrs")]:
                fig.add_hline(y=y_val, line_dash="dot", line_color="#aaa",
                              annotation_text=label, annotation_position="right")
            fig.update_layout(yaxis=dict(title="Days to Final Order", tickformat=","),
                              hovermode="x unified", height=420, margin=dict(t=60, b=40))
            fig = _add_admin_bands(fig)
            st.plotly_chart(fig, width="stretch")

        with at2:
            fig2 = go.Figure()
            for col_k, name, color in [
                ("detained_median",    "Detained",               "#c0392b"),
                ("nondetained_median", "Non-Detained",           "#2980b9"),
                ("represented_median", "Represented",            "#1e8a50"),
                ("prose_median",       "Pro Se (unrepresented)", "#e67e22"),
            ]:
                fig2.add_trace(go.Scatter(
                    x=age_f["fiscal_year"], y=age_f[col_k],
                    mode="lines+markers", name=name,
                    line=dict(color=color, width=2.5), marker=dict(size=5),
                    hovertemplate=f"FY%{{x}} — {name}: %{{y:,.0f}} days<extra></extra>"))
            fig2.update_layout(yaxis=dict(title="Median Days", tickformat=","),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400, margin=dict(t=60, b=40))
            fig2 = _add_admin_bands(fig2)
            st.plotly_chart(fig2, width="stretch")

            latest_row = age_f.iloc[-1]
            compare_data = {
                "Group": ["Detained", "Non-Detained", "Represented", "Pro Se"],
                "Median Days": [latest_row["detained_median"], latest_row["nondetained_median"],
                                latest_row["represented_median"], latest_row["prose_median"]],
                "Color": ["#c0392b", "#2980b9", "#1e8a50", "#e67e22"],
            }
            comp_df = pd.DataFrame(compare_data).sort_values("Median Days")
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=comp_df["Median Days"], y=comp_df["Group"], orientation="h",
                marker_color=comp_df["Color"].tolist(),
                text=[f"{int(d):,}d ({d/365:.1f} yrs)" for d in comp_df["Median Days"]],
                textposition="outside",
                hovertemplate="<b>%{y}</b>: %{x:,.0f} days<extra></extra>"))
            fig3.update_layout(xaxis=dict(title="Median Days", tickformat=","),
                height=240, margin=dict(l=140, r=120, t=20, b=40))
            st.plotly_chart(fig3, width="stretch")

        with at3:
            if court_age_df is None or court_age_df.empty:
                st.info("Court-level data not available.")
            else:
                crt = court_age_df.sort_values("median_days", ascending=True)
                fig4 = go.Figure()
                fig4.add_trace(go.Bar(
                    x=crt["median_days"], y=crt["court_city"], orientation="h",
                    text=[f"{int(v):,}d ({v/365:.1f}yr)" for v in crt["median_days"]],
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Median: %{x:,.0f}d<br>Pending: %{customdata[0]:,}<extra></extra>",
                    customdata=crt[["total_pending"]].values,
                    marker_color="#c0392b"))
                fig4.update_layout(xaxis=dict(title="Median Days", tickformat=","),
                    height=max(380, len(crt) * 25 + 80),
                    margin=dict(l=160, r=100, t=40, b=40))
                st.plotly_chart(fig4, width="stretch")

        with at4:
            if age_dist_df is None or age_dist_df.empty:
                st.info("Backlog age distribution not available.")
            else:
                total_p = age_dist_df["count"].sum()
                col_d, col_b = st.columns([1, 2])
                with col_d:
                    fig5 = go.Figure(go.Pie(
                        labels=age_dist_df["age_bucket"], values=age_dist_df["count"],
                        marker_colors=age_dist_df["color"].tolist(), hole=0.52,
                        texttemplate="%{label}<br>%{percent}", textposition="outside",
                        hovertemplate="<b>%{label}</b><br>%{value:,} cases<extra></extra>"))
                    fig5.add_annotation(text=f"<b>{format_num(total_p)}</b><br>pending",
                        x=0.5, y=0.5, showarrow=False, font=dict(size=15))
                    fig5.update_layout(showlegend=False, height=340,
                                       margin=dict(t=20, b=20, l=20, r=20))
                    st.plotly_chart(fig5, width="stretch")
                with col_b:
                    fig6 = go.Figure()
                    fig6.add_trace(go.Bar(
                        x=age_dist_df["age_bucket"], y=age_dist_df["count"],
                        marker_color=age_dist_df["color"].tolist(),
                        text=[format_num(v) for v in age_dist_df["count"]],
                        textposition="outside"))
                    fig6.update_layout(yaxis=dict(title="Pending Cases", tickformat=","),
                                       height=340, margin=dict(t=20, b=60))
                    st.plotly_chart(fig6, width="stretch")

                over5 = age_dist_df[age_dist_df["age_bucket"].isin(
                    ["5–10 years", "Over 10 years"])]["count"].sum()
                st.info(
                    f"**{format_num(over5)} pending cases** ({over5/total_p:.0%}) have been "
                    "waiting 5+ years.",
                    icon="📅",
                )

        csv_download_button(age_df, "relief_docket_case_age_timeline.csv", key="age_dl")
        if court_age_df is not None:
            csv_download_button(court_age_df, "relief_docket_case_age_by_court.csv",
                                key="age_court_dl")

add_gavel_glimpse_footer()
