"""
pages/F_Judges.py — Judges (merged)

Tab 1: Overview  — sorted grant rate chart + table (from page 2)
Tab 2: Compare   — side-by-side comparison, radar, grouped bar (from page 11)
Tab 3: Performance — distribution, scatter, refugee roulette, individual profile (from page 18)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from utils import add_sidebar, no_data_banner, format_pct, format_num, csv_download_button
from utils.data_loader import load_judge_metrics, get_pipeline_status, has_any_data
from utils.charts import judge_grant_rate_chart
from footer import add_gavel_glimpse_footer

add_sidebar("judges")

st.title("👨‍⚖️ Judges")
st.caption(
    "Immigration judge profiles, head-to-head comparison, and deep-dive statistical analysis "
    "of grant rate distributions."
)

status = get_pipeline_status()
if status.get("seed_mode"):
    st.warning(
        "**Seed mode** — judge names and individual statistics shown here are **synthetic** "
        "(generated from court-level distributions for demonstration). "
        "Real judge-level data requires the full EOIR pipeline.",
        icon="⚠️",
    )

# ── Load once, share across all tabs ─────────────────────────────────────────
raw_df = load_judge_metrics()

if raw_df is None or raw_df.empty:
    no_data_banner()
else:
    # ── Derived columns (used by all tabs) ────────────────────────────────────
    df = raw_df.copy()
    df["grant_pct"]   = (df["asylum_grant_rate"] * 100).round(2)
    df["removal_pct"] = (df["removal_rate"]       * 100).round(2)
    df["abs_pct"]     = (df["in_absentia_rate"]   * 100).round(2)
    df["rep_pct"]     = (df["representation_rate"]* 100).round(2)
    df["label"]       = df["judge_name"] + " — " + df["court_city"]

    court_stats = (
        df.groupby("court_city")["grant_pct"]
        .agg(court_mean="mean", court_std="std", court_median="median",
             court_min="min", court_max="max", court_n="count")
        .reset_index()
    )
    df = df.merge(court_stats, on="court_city", how="left")
    df["z_score"]    = ((df["grant_pct"] - df["court_mean"]) /
                        df["court_std"].replace(0, np.nan)).fillna(0).round(2)
    df["is_outlier"] = df["z_score"].abs() >= 1.5

    # ── Shared sidebar filters ────────────────────────────────────────────────
    st.sidebar.markdown("### Judge Filters")
    circuits_avail = sorted(df["circuit"].dropna().unique())
    sel_circuits = st.sidebar.multiselect("Circuit", circuits_avail,
                                           default=circuits_avail, key="j_circuits")
    courts_avail = sorted(df[df["circuit"].isin(sel_circuits)]["court_city"].dropna().unique())
    sel_courts   = st.sidebar.multiselect("Court", courts_avail,
                                           default=courts_avail, key="j_courts")
    min_cases_sb = st.sidebar.slider("Min total cases", 0,
                                     int(df["total_cases"].max()), 0,
                                     step=50, key="j_min_cases")
    grant_range = st.sidebar.slider("Grant rate range (%)", 0, 100, (0, 100),
                                     step=1, key="j_grant_range")

    fdf = df[
        df["circuit"].isin(sel_circuits)
        & df["court_city"].isin(sel_courts)
        & (df["total_cases"] >= min_cases_sb)
        & (df["grant_pct"] >= grant_range[0])
        & (df["grant_pct"] <= grant_range[1])
    ].copy()

    st.markdown(f"**{len(fdf)} judges** · **{fdf['court_city'].nunique()} courts** visible with current filters.")

    tab_ov, tab_cmp, tab_perf = st.tabs(["📊 Overview", "⚖️ Compare", "🔬 Performance"])

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1: OVERVIEW
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_ov:
        st.subheader("Immigration Judge Overview")
        st.markdown(
            "Asylum grant rates, removal rates, and caseloads for individual immigration judges. "
        )

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            min_cases_ov = st.slider("Minimum case count (for chart)", 10, 500, 50,
                                     key="j_min_cases_ov")
        with col_f2:
            sort_map = {
                "Total Cases": "total_cases",
                "Asylum Grant Rate": "asylum_grant_rate",
                "Removal Rate": "removal_rate",
                "In Absentia Rate": "in_absentia_rate"
            }
            sort_display = st.selectbox(
                "Sort by",
                list(sort_map.keys()),
                key="j_sort",
            )
            sort_by = sort_map[sort_display]

        filtered_ov = fdf[fdf["total_cases"] >= min_cases_ov].copy()

        ov_t1, ov_t2 = st.tabs(["📊 Chart", "📋 Table"])

        with ov_t1:
            fig = judge_grant_rate_chart(filtered_ov, top_n=30)
            if fig:
                st.plotly_chart(fig, width='stretch')

        with ov_t2:
            display_cols = [c for c in [
                "judge_name", "judge_code", "total_cases",
                "asylum_grant_rate", "removal_rate", "in_absentia_rate",
            ] if c in filtered_ov.columns]
            display_df = filtered_ov[display_cols].sort_values(sort_by, ascending=False).copy()
            for col in ["asylum_grant_rate", "removal_rate", "in_absentia_rate"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda v: f"{v*100:.1f}%")
            st.dataframe(display_df, width='stretch', height=500)

        with st.expander("Why judge-level data matters"):
            st.markdown("""
The asylum grant rate variation between judges at the same court can be enormous.
TRAC at Syracuse has documented cases where judges at the same court have grant rates
ranging from under 5% to over 90% for similar nationalities and case types.

This variation — sometimes called the "refugee roulette" problem — is one of the
most well-documented and least-justified disparities in the U.S. legal system.
            """)

        csv_download_button(fdf, "relief_docket_judges.csv", key="j_dl_ov")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2: COMPARE
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_cmp:
        st.subheader("Compare Judges Side by Side")
        st.markdown(
            "Select two or more immigration judges to compare their grant rates, removal rates, "
            "and caseload statistics side by side."
        )

        col_map = {
            "Grant Rate %":       "grant_pct",
            "Removal Rate %":     "removal_pct",
            "In Absentia Rate %": "abs_pct",
            "Total Cases":        "total_cases",
            "Years on Bench":     "years_on_bench",
        }
        sort_col = st.selectbox("Sort ranking table by",
            list(col_map.keys()), index=0, key="j_cmp_sort")
        fdf_sorted = fdf.sort_values(col_map[sort_col],
            ascending=(sort_col != "Grant Rate %"))

        display_tbl = fdf_sorted[[
            "judge_name", "court_city", "circuit",
            "total_cases", "grant_pct", "removal_pct", "abs_pct", "rep_pct", "years_on_bench",
        ]].copy()
        display_tbl.columns = ["Judge", "Court", "Circuit",
            "Cases", "Grant %", "Removal %", "In Absentia %", "Represented %", "Yrs"]
        st.dataframe(
            display_tbl, width='stretch', hide_index=True,
            column_config={
                "Grant %":       st.column_config.ProgressColumn("Grant %",    min_value=0, max_value=100, format="%.1f%%"),
                "Removal %":     st.column_config.ProgressColumn("Removal %",  min_value=0, max_value=100, format="%.1f%%"),
                "In Absentia %": st.column_config.ProgressColumn("In Absentia %", min_value=0, max_value=100, format="%.1f%%"),
            },
        )

        st.markdown("---")
        judge_options_cmp = fdf_sorted["label"].tolist()
        default_picks = judge_options_cmp[:min(2, len(judge_options_cmp))]
        selected_labels = st.multiselect(
            "Pick 2–4 judges to compare",
            options=judge_options_cmp,
            default=default_picks,
            max_selections=4,
            key="j_cmp_select",
        )

        if len(selected_labels) < 2:
            st.info("Select at least 2 judges above to see the comparison.", icon="ℹ️")
        else:
            comp = fdf[fdf["label"].isin(selected_labels)].copy()
            metrics = ["grant_pct", "removal_pct", "abs_pct", "rep_pct"]
            metric_labels = {
                "grant_pct":   "Grant Rate %",
                "removal_pct": "Removal Rate %",
                "abs_pct":     "In Absentia Rate %",
                "rep_pct":     "Represented %",
            }
            colors = ["#1e8a50", "#c0392b", "#e67e22", "#2980b9", "#8e44ad"]

            fig_bar = go.Figure()
            for i, (_, row) in enumerate(comp.iterrows()):
                fig_bar.add_bar(
                    name=row["judge_name"],
                    x=[metric_labels[m] for m in metrics],
                    y=[row[m] for m in metrics],
                    marker_color=colors[i % len(colors)],
                    hovertemplate="%{x}: %{y:.1f}%<extra>" + row["judge_name"] + "</extra>",
                )
            fig_bar.update_layout(
                barmode="group", yaxis_title="Rate (%)",
                title="Key Metrics Comparison",
                legend=dict(orientation="h", y=1.12),
                height=400, margin=dict(l=0, r=0, t=50, b=0),
            )
            st.plotly_chart(fig_bar, width='stretch')

            radar_metrics = ["Grant %", "Removal %", "In Absentia %", "Represented %"]
            fig_radar = go.Figure()
            for i, (_, row) in enumerate(comp.iterrows()):
                vals = [row["grant_pct"], row["removal_pct"], row["abs_pct"], row["rep_pct"]]
                fig_radar.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=radar_metrics + [radar_metrics[0]],
                    fill="toself", name=row["judge_name"],
                    line_color=colors[i % len(colors)], opacity=0.7,
                ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title="Metric Radar", legend=dict(orientation="h", y=-0.15),
                height=430, margin=dict(l=20, r=20, t=50, b=60),
            )
            st.plotly_chart(fig_radar, width='stretch')

            st.markdown("### Detailed Stats")
            cmp_cols = st.columns(len(comp))
            for col_c, (_, row) in zip(cmp_cols, comp.iterrows()):
                with col_c:
                    with st.container(border=True):
                        st.markdown(f"**{row['judge_name']}**")
                        st.caption(f"{row['court_city']} · {row['circuit']} Circuit")
                        st.metric("Grant Rate",     f"{row['grant_pct']:.1f}%")
                        st.metric("Removal Rate",   f"{row['removal_pct']:.1f}%")
                        st.metric("In Absentia",    f"{row['abs_pct']:.1f}%")
                        st.metric("Represented",    f"{row['rep_pct']:.1f}%")
                        st.metric("Total Cases",    f"{row['total_cases']:,}")
                        st.metric("Years on Bench", str(int(row["years_on_bench"])))

        st.caption(
            "In seed mode, judge names and statistics are synthetic. "
            "Real judge-level data is available via the full EOIR pipeline."
        )
        csv_download_button(fdf, "relief_docket_judges_compare.csv", key="j_cmp_dl")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 3: PERFORMANCE DEEP-DIVE
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_perf:
        st.subheader("Judge Performance Deep-Dive")
        st.caption(
            "Statistical analysis of immigration judge outcomes — grant rate distributions, "
            "outlier detection, and metric correlations."
        )

        national_median = fdf["grant_pct"].median()
        national_spread = fdf["grant_pct"].max() - fdf["grant_pct"].min()
        n_outliers      = fdf["is_outlier"].sum()

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("National Median Grant Rate", f"{national_median:.1f}%")
        p2.metric("Overall Spread (Max − Min)", f"{national_spread:.1f} pp")
        p3.metric("Outlier Judges", int(n_outliers),
                  help="Judges ≥ 1.5 SD from their court average")
        p4.metric("Judges Visible", len(fdf), delta_color="off")

        pt1, pt2, pt3, pt4 = st.tabs([
            "📦 Distribution by Court", "🔭 Scatter Analysis",
            "🎲 Refugee Roulette", "🧑‍⚖️ Individual Profile",
        ])

        # Distribution by court
        with pt1:
            st.subheader("Grant Rate Distribution Within Each Court")
            st.caption("Wide boxes = high variance = unpredictable outcomes for respondents.")
            courts_ordered = (
                fdf.groupby("court_city")["grant_pct"]
                .median().sort_values(ascending=True).index.tolist()
            )
            circuit_colors = {
                "1st": "#2980b9", "2nd": "#1e8a50", "3rd": "#8e44ad",
                "4th": "#e67e22", "5th": "#c0392b", "6th": "#16a085",
                "7th": "#2c3e50", "8th": "#d35400", "9th": "#27ae60",
                "10th": "#8e44ad", "11th": "#2980b9",
            }
            circuit_by_court = fdf.groupby("court_city")["circuit"].first().to_dict()
            fig_box = go.Figure()
            for court in courts_ordered:
                vals  = fdf[fdf["court_city"] == court]["grant_pct"].tolist()
                circ  = circuit_by_court.get(court, "?")
                color = circuit_colors.get(circ, "#555")
                fig_box.add_trace(go.Box(
                    y=vals, name=court,
                    marker_color=color, line_color=color,
                    boxpoints="outliers",
                    hovertemplate=f"<b>{court}</b> ({circ} Circuit)<br>Grant rate: %{{y:.1f}}%<extra></extra>",
                ))
            fig_box.update_layout(
                xaxis=dict(tickangle=-25),
                yaxis=dict(title="Asylum Grant Rate (%)", ticksuffix="%"),
                showlegend=False, height=480,
                margin=dict(t=20, b=100, l=40, r=20),
            )
            st.plotly_chart(fig_box, width="stretch")
            tbl_box = (
                fdf.groupby(["court_city", "circuit"]).agg(
                    Judges=("judge_name", "count"),
                    Median=("grant_pct", "median"),
                    Mean=("grant_pct", "mean"),
                    SD=("grant_pct", "std"),
                    Min=("grant_pct", "min"),
                    Max=("grant_pct", "max"),
                ).round(1).reset_index()
                .rename(columns={"court_city": "Court", "circuit": "Circuit"})
                .sort_values("Median", ascending=False)
            )
            tbl_box["Spread"] = (tbl_box["Max"] - tbl_box["Min"]).round(1)
            with st.expander("Court-level summary table"):
                st.dataframe(tbl_box, width="stretch", hide_index=True,
                    column_config={
                        "Median": st.column_config.ProgressColumn(
                            "Median %", min_value=0, max_value=100, format="%.1f%%"),
                        "SD":     st.column_config.NumberColumn("Std Dev", format="%.1f"),
                        "Spread": st.column_config.NumberColumn("Spread (pp)", format="%.1f"),
                    })

        # Scatter analysis
        with pt2:
            st.subheader("Correlation Analysis")
            st.caption("Each dot is one judge. Explore relationships between grant rate and other factors.")
            scatter_map = {
                "Representation Rate (%)": "rep_pct",
                "Total Cases (Caseload Volume)": "total_cases",
                "Years On Bench": "years_on_bench",
                "In Absentia Rate (%)": "abs_pct"
            }
            scatter_display = st.selectbox(
                "X-axis variable",
                options=list(scatter_map.keys()),
                key="j_perf_scatter",
            )
            scatter_x = scatter_map[scatter_display]
            axis_labels_p = {
                "rep_pct":        "Representation Rate (%)",
                "total_cases":    "Total Cases",
                "years_on_bench": "Years on Bench",
                "abs_pct":        "In Absentia Rate (%)",
            }
            fig_scat = px.scatter(
                fdf, x=scatter_x, y="grant_pct",
                color="court_city", size="total_cases", size_max=20,
                hover_data={"judge_name": True, "court_city": True, "circuit": True,
                            "total_cases": ":,", "grant_pct": ":.1f",
                            "rep_pct": ":.1f", "years_on_bench": True, "is_outlier": True},
                labels={scatter_x: axis_labels_p[scatter_x],
                        "grant_pct": "Asylum Grant Rate (%)", "court_city": "Court"},
                symbol="is_outlier", symbol_map={True: "star", False: "circle"},
                trendline="ols", trendline_color_override="#c0392b",
            )
            fig_scat.update_layout(height=480, legend=dict(orientation="h", y=-0.2),
                                   margin=dict(t=20, b=60))
            st.plotly_chart(fig_scat, width="stretch")
            valid = fdf[[scatter_x, "grant_pct"]].dropna()
            if len(valid) > 3:
                corr = valid.corr().iloc[0, 1]
                direction = "positive" if corr > 0 else "negative"
                strength  = "strong" if abs(corr) > 0.5 else ("moderate" if abs(corr) > 0.3 else "weak")
                st.caption(f"Pearson r = **{corr:.2f}** — {strength} {direction} correlation.")

        # Refugee roulette
        with pt3:
            st.subheader('The "Refugee Roulette" Problem')
            st.caption(
                "Coined by Ramji-Nogales, Schoenholtz & Schrag (2007) — similarly-situated "
                "asylum applicants receive drastically different outcomes based on which judge "
                "hears their case."
            )
            spread_df = (
                fdf.groupby(["court_city", "circuit"]).agg(
                    spread=("grant_pct", lambda x: x.max() - x.min()),
                    std=("grant_pct", "std"),
                    n=("judge_name", "count"),
                    median=("grant_pct", "median"),
                ).round(1).reset_index().sort_values("spread", ascending=False)
            )
            spread_df["color"] = spread_df["spread"].apply(
                lambda v: "#c0392b" if v >= 40 else ("#e67e22" if v >= 25 else "#1e8a50")
            )
            fig_rr = go.Figure()
            fig_rr.add_trace(go.Bar(
                x=spread_df["court_city"], y=spread_df["spread"],
                marker_color=spread_df["color"].tolist(),
                text=[f"{v:.0f} pp" for v in spread_df["spread"]],
                textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>Spread: %{y:.1f} pp<br>"
                    "Std Dev: %{customdata[0]:.1f} pp<br>Judges: %{customdata[1]}<br>"
                    "Median grant: %{customdata[2]:.1f}%<extra></extra>"),
                customdata=spread_df[["std", "n", "median"]].values,
            ))
            fig_rr.add_hline(y=30, line_dash="dot", line_color="#c0392b",
                             annotation_text="High risk threshold (30 pp)",
                             annotation_position="top right")
            fig_rr.update_layout(
                yaxis=dict(title="Within-Court Grant Rate Spread (pp)", ticksuffix=" pp"),
                xaxis_tickangle=-30, height=400, margin=dict(t=20, b=80))
            st.plotly_chart(fig_rr, width="stretch")

            st.subheader("Statistical Outlier Judges")
            outlier_df = fdf[fdf["is_outlier"]].sort_values("z_score", key=abs, ascending=False)[
                ["judge_name", "court_city", "circuit", "grant_pct", "court_mean", "z_score",
                 "total_cases", "years_on_bench"]].copy()
            outlier_df.columns = ["Judge", "Court", "Circuit", "Grant %", "Court Avg %",
                                   "Z-Score", "Total Cases", "Yrs on Bench"]
            outlier_df["Direction"] = outlier_df["Z-Score"].apply(
                lambda z: "🟢 More lenient" if z > 0 else "🔴 Stricter")
            st.dataframe(outlier_df, width="stretch", hide_index=True,
                column_config={
                    "Grant %":     st.column_config.ProgressColumn(
                        "Grant %", min_value=0, max_value=100, format="%.1f%%"),
                    "Court Avg %": st.column_config.NumberColumn("Court Avg", format="%.1f%%"),
                    "Z-Score":     st.column_config.NumberColumn("Z-Score", format="%.2f"),
                })
            st.caption(f"**{len(outlier_df)} judges** out of {len(fdf)} visible are outliers (|Z| ≥ 1.5).")
            with st.expander("Research background — Refugee Roulette"):
                st.markdown("""
### Ramji-Nogales, Schoenholtz & Schrag (2007)

The seminal study analyzed 140,000 asylum decisions from 2000–2004. Key findings:

- At a single Chicago court, judge grant rates ranged from **10% to 79%** for similar cases
- Nationally, applicants from the same country had grant rates varying by **40+ pp** across courts
- Which judge a person drew was a **stronger predictor of outcome than the facts of their case**

**Why the variance persists:** IJ hiring by era, no jury, case assignment practices, and
wide fact-finding discretion all contribute. Raw grant rates do **not** control for nationality
mix, representation, or case era — use TRAC Immigration's controlled statistics for
practitioner use.
                """)

        # Individual profile
        with pt4:
            st.subheader("Individual Judge Profile")
            search_input = st.text_input(
                "Search judge name", placeholder="Type a judge's last name…",
                key="j_perf_search",
            )
            if search_input:
                candidates = df[df["judge_name"].str.contains(search_input, case=False, na=False)]
            else:
                candidates = fdf.copy()

            if candidates.empty:
                st.info(f'No judges matching "{search_input}".')
            else:
                judge_options_p = sorted(candidates["label"].unique())
                selected_label  = st.selectbox("Select judge", judge_options_p,
                                               key="j_perf_select")
                judge_row = df[df["label"] == selected_label].iloc[0]

                col_card, col_ctx = st.columns([1, 2])
                with col_card:
                    with st.container(border=True):
                        st.markdown(f"### 🧑‍⚖️ {judge_row['judge_name']}")
                        st.caption(f"{judge_row['court_city']} · {judge_row['circuit']} Circuit")
                        st.metric("Asylum Grant Rate",   f"{judge_row['grant_pct']:.1f}%",
                                  delta=f"{judge_row['grant_pct'] - judge_row['court_mean']:+.1f} pp vs. court avg")
                        st.metric("Removal Rate",        f"{judge_row['removal_pct']:.1f}%")
                        st.metric("In Absentia Rate",    f"{judge_row['abs_pct']:.1f}%")
                        st.metric("Represented Cases",   f"{judge_row['rep_pct']:.1f}%")
                        st.metric("Total Cases Decided", f"{judge_row['total_cases']:,}")
                        st.metric("Years on Bench",      str(int(judge_row["years_on_bench"])))
                        if judge_row["is_outlier"]:
                            direction = "more lenient" if judge_row["z_score"] > 0 else "stricter"
                            st.warning(
                                f"Statistical outlier — **{abs(judge_row['z_score']):.1f}σ** "
                                f"{direction} than court average.",
                                icon="⚠️",
                            )

                with col_ctx:
                    compare_rows = [
                        {"label": judge_row["judge_name"],        "type": "This Judge",    "grant_pct": judge_row["grant_pct"]},
                        {"label": f"{judge_row['court_city']} avg","type": "Court Average","grant_pct": judge_row["court_mean"]},
                        {"label": "National median",               "type": "National",     "grant_pct": fdf["grant_pct"].median()},
                    ]
                    cdf2 = pd.DataFrame(compare_rows)
                    color_map = {"This Judge": "#2980b9", "Court Average": "#e67e22", "National": "#888"}
                    fig_card = go.Figure()
                    for _, r2 in cdf2.iterrows():
                        fig_card.add_trace(go.Bar(
                            x=[r2["label"]], y=[r2["grant_pct"]],
                            name=r2["type"], marker_color=color_map[r2["type"]],
                            text=f"{r2['grant_pct']:.1f}%", textposition="outside",
                            hovertemplate=f"{r2['type']}: {r2['grant_pct']:.1f}%<extra></extra>",
                        ))
                    fig_card.update_layout(
                        yaxis=dict(title="Asylum Grant Rate (%)", range=[0, 100], ticksuffix="%"),
                        showlegend=False, height=320,
                        margin=dict(t=20, b=20, l=40, r=20),
                    )
                    st.plotly_chart(fig_card, width="stretch")

                    court_judges = df[df["court_city"] == judge_row["court_city"]].copy()
                    court_sorted = court_judges.sort_values("grant_pct")
                    fig_rank = go.Figure()
                    fig_rank.add_trace(go.Bar(
                        x=court_sorted["judge_name"], y=court_sorted["grant_pct"],
                        marker_color=[
                            "#2980b9" if n == judge_row["judge_name"] else "#c8d6e5"
                            for n in court_sorted["judge_name"]
                        ],
                        text=[f"{v:.0f}%" for v in court_sorted["grant_pct"]],
                        textposition="outside",
                        hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
                    ))
                    fig_rank.update_layout(
                        title=f"All judges at {judge_row['court_city']} — Grant Rate Ranking",
                        yaxis=dict(title="Grant Rate (%)", range=[0, 100], ticksuffix="%"),
                        xaxis_tickangle=-30, height=300,
                        margin=dict(t=40, b=80, l=40, r=20),
                    )
                    st.plotly_chart(fig_rank, width="stretch")

        with st.expander("📋 Data sources & methodology"):
            st.markdown("""
**Primary sources:**
- **EOIR CASE database** (full pipeline) — individual judge disposition records
- **TRAC Immigration** (tracreports.org) — judge-level grant rate analysis, nationality-controlled
- **Ramji-Nogales, Schoenholtz & Schrag (2007)** — "Refugee Roulette", Stanford Law Review

**Methodology notes:**
- Outlier detection uses ±1.5 standard deviations from the court mean grant rate
- Z-scores are computed within courts (not nationally) to control for court-level differences
- Seed data uses court-level distributions from EOIR yearbooks; individual judge names are fictional
- Raw grant rates do not control for nationality mix, representation, or case era
            """)

        csv_download_button(fdf, "relief_docket_judges_performance.csv", key="j_perf_dl")

add_gavel_glimpse_footer()
