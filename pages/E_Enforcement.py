"""
pages/E_Enforcement.py — Enforcement (merged)

Tab 1: In Absentia — failure-to-appear orders trend and representation gap
Tab 2: Detention — population, facilities, avg length of stay
Tab 3: Removals — removal order types, nationalities
Tab 4: Bond — bond grant rates, amounts, detention rate
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import add_sidebar, no_data_banner, format_num, format_pct, csv_download_button
from utils.data_loader import (
    load_in_absentia_timeline, load_in_absentia_by_court,
    load_detention_timeline, load_detention_by_facility,
    load_removal_orders, load_removal_by_nationality,
    load_bond_analytics,
    get_pipeline_status,
)
from utils.charts import _add_admin_bands
from footer import add_gavel_glimpse_footer

# ── Removal type constants (from page 15) ────────────────────────────────────
TYPE_COLORS = {
    "Ordered Removed (IJ)":           "#c0392b",
    "Reinstated Removal":              "#8e44ad",
    "Administrative Removal":          "#e67e22",
    "Voluntary Departure (Departed)":  "#1e8a50",
    "Expedited Removal (CBP/ICE)":     "#2980b9",
}
TYPE_LABELS = {
    "Ordered Removed (IJ)":           "IJ Removal Order",
    "Reinstated Removal":              "Reinstated (prior order)",
    "Administrative Removal":          "Admin Removal (no IJ)",
    "Voluntary Departure (Departed)":  "Voluntary Departure",
    "Expedited Removal (CBP/ICE)":     "Expedited (border)",
}

add_sidebar("enforcement")

st.title("🔒 Enforcement")
st.caption(
    "Immigration enforcement outcomes: failure-to-appear orders, civil immigration detention, "
    "removal pathways, and bond proceedings."
)

status = get_pipeline_status()
if status.get("seed_mode"):
    st.warning(
        "**Seed mode** — statistics sourced from EOIR Yearbooks, ICE Detention Statistics, "
        "DHS Yearbook of Immigration Statistics, and TRAC Immigration data.",
        icon="⚠️",
    )

# Load all data up-front
ia_time_df  = load_in_absentia_timeline()
ia_court_df = load_in_absentia_by_court()
det_time_df = load_detention_timeline()
det_fac_df  = load_detention_by_facility()
rem_df      = load_removal_orders()
rem_nat_df  = load_removal_by_nationality()
bond_df     = load_bond_analytics()

tab_ia, tab_det, tab_rem, tab_bond = st.tabs([
    "🚫 In Absentia", "🔒 Detention", "🛫 Removals", "⚖️ Bond"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: IN ABSENTIA
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ia:
    st.subheader("In Absentia Orders")
    st.markdown(
        "When a respondent fails to appear for a scheduled hearing, "
        "the immigration judge may issue a **removal order in absentia** under INA §240(b)(5)."
    )
    if ia_time_df is None or ia_time_df.empty:
        no_data_banner()
    else:
        ia_sorted = ia_time_df.sort_values("fiscal_year")
        li = ia_sorted.iloc[-1]
        pi = ia_sorted.iloc[-2] if len(ia_sorted) > 1 else li

        ic1, ic2, ic3 = st.columns(3)
        ic1.metric(f"In Absentia Orders (FY{int(li['fiscal_year'])})",
                   format_num(li["in_absentia_orders"]),
                   delta=f"{int(li['in_absentia_orders'] - pi['in_absentia_orders']):+,}",
                   delta_color="inverse")
        ic2.metric("In Absentia Rate",
                   format_pct(li["in_absentia_rate"]),
                   delta=f"{(li['in_absentia_rate'] - pi['in_absentia_rate'])*100:+.1f}pp",
                   delta_color="inverse")
        if "unrepresented_ia_rate" in li and "represented_ia_rate" in li:
            ic3.metric("Pro Se vs Represented IA Rate",
                       f"{li['unrepresented_ia_rate']/li['represented_ia_rate']:.1f}×")

        iat1, iat2, iat3 = st.tabs(["📈 Annual Trend", "👤 Representation Gap", "🏛️ By Court"])

        with iat1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=ia_sorted["fiscal_year"], y=ia_sorted["in_absentia_orders"],
                name="In Absentia Orders", marker_color="#c0392b", opacity=0.8,
                yaxis="y",
                hovertemplate="FY%{x} — %{y:,} orders<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=ia_sorted["fiscal_year"], y=ia_sorted["in_absentia_rate"],
                name="IA Rate (right)", mode="lines+markers",
                line=dict(color="#e67e22", width=2), yaxis="y2",
                hovertemplate="FY%{x} — %{y:.1%}<extra></extra>"))
            fig.update_layout(
                yaxis=dict(title="Orders (count)", tickformat=","),
                yaxis2=dict(title="IA Rate (%)", tickformat=".0%",
                            overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.1),
                hovermode="x unified", height=420, margin=dict(t=60, b=40))
            fig = _add_admin_bands(fig)
            st.plotly_chart(fig, width="stretch")

        with iat2:
            if "unrepresented_ia_rate" in ia_sorted.columns and "represented_ia_rate" in ia_sorted.columns:
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=ia_sorted["fiscal_year"], y=ia_sorted["unrepresented_ia_rate"],
                    mode="lines+markers", name="Pro Se IA Rate",
                    line=dict(color="#e67e22", width=2.5),
                    hovertemplate="FY%{x} — Pro Se IA: %{y:.1%}<extra></extra>"))
                fig2.add_trace(go.Scatter(
                    x=ia_sorted["fiscal_year"], y=ia_sorted["represented_ia_rate"],
                    mode="lines+markers", name="Represented IA Rate",
                    line=dict(color="#1e8a50", width=2.5, dash="dash"),
                    hovertemplate="FY%{x} — Represented IA: %{y:.1%}<extra></extra>"))
                fig2.update_layout(
                    yaxis=dict(title="In Absentia Rate", tickformat=".0%"),
                    hovermode="x unified", legend=dict(orientation="h", y=1.1),
                    height=360, margin=dict(t=60, b=40))
                fig2 = _add_admin_bands(fig2)
                st.plotly_chart(fig2, width="stretch")
                st.info(
                    "Unrepresented respondents miss hearings at dramatically higher rates. "
                    "Address notification issues, complex hearing schedules, and inability to track "
                    "NTA requirements without an attorney all contribute to this gap.",
                    icon="📋",
                )
            else:
                st.info("Representation breakdown data not available.")

        with iat3:
            if ia_court_df is None or ia_court_df.empty:
                st.info("Court-level in absentia data not available.")
            else:
                ia_c = ia_court_df.sort_values("in_absentia_rate", ascending=True)
                fig3 = px.bar(ia_c, x="in_absentia_rate", y="court_city", orientation="h",
                    color="in_absentia_rate", color_continuous_scale="Reds",
                    text=ia_c["in_absentia_rate"].map("{:.1%}".format),
                    labels={"in_absentia_rate": "IA Rate", "court_city": "Court"})
                fig3.update_coloraxes(showscale=False)
                fig3.update_traces(textposition="outside")
                fig3.update_layout(yaxis=dict(autorange="reversed"),
                    height=max(380, len(ia_c)*25 + 80), margin=dict(t=20, b=40))
                st.plotly_chart(fig3, width="stretch")
        csv_download_button(ia_time_df, "relief_docket_in_absentia.csv", key="ia_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: DETENTION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_det:
    st.subheader("Civil Immigration Detention")
    st.markdown(
        "ICE detains individuals in civil immigration custody pending removal proceedings. "
        "Detention is **civil, not criminal** — there is no constitutional right to "
        "appointed counsel."
    )
    if det_time_df is None or det_time_df.empty:
        no_data_banner()
    else:
        det_s_all = det_time_df.sort_values("fiscal_year").copy()
        det_s = det_s_all[det_s_all["book_ins"].fillna(0) >= 100].copy()
        if det_s.empty:
            det_s = det_s_all.copy()
        ld = det_s.iloc[-1]
        pd_det = det_s.iloc[-2] if len(det_s) > 1 else ld
        avg_los = ld.get("avg_length_of_stay_days")

        dc1, dc2, dc3 = st.columns(3)
        dc1.metric(f"ADP (FY{int(ld['fiscal_year'])})",
                   format_num(ld["avg_daily_pop"]),
                   delta=f"{int(ld['avg_daily_pop'] - pd_det['avg_daily_pop']):+,}",
                   delta_color="inverse")
        dc2.metric("Book-ins", format_num(ld["book_ins"]))
        if pd.notna(avg_los):
            dc3.metric("Avg. Length of Stay", f"{avg_los:.1f} days")
        else:
            dc3.metric("Avg. Length of Stay", "Not available")
        if len(det_s) != len(det_s_all):
            st.caption("Tiny partial-year detention buckets are excluded from headline metrics and charts.")

        dt1, dt2, dt3 = st.tabs(["👥 Population & Beds", "📋 Book-ins & Length of Stay",
                                   "🏢 Facility Types"])

        with dt1:
            fig = go.Figure()
            if "detention_beds_funded" in det_s.columns:
                fig.add_trace(go.Scatter(
                    x=det_s["fiscal_year"], y=det_s["detention_beds_funded"],
                    fill="tozeroy", fillcolor="rgba(127,140,141,0.15)",
                    line=dict(color="#aaa", width=1.5, dash="dot"),
                    name="Bed Capacity",
                    hovertemplate="FY%{x} — Capacity: %{y:,}<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=det_s["fiscal_year"], y=det_s["avg_daily_pop"],
                mode="lines+markers", name="Avg Daily Population",
                line=dict(color="#c0392b", width=2.5),
                fill="tozeroy", fillcolor="rgba(192,57,43,0.15)",
                hovertemplate="FY%{x} — ADP: %{y:,}<extra></extra>"))
            fig.update_layout(
                yaxis=dict(title="Detainees", tickformat=","),
                hovermode="x unified", height=400, margin=dict(t=60, b=40))
            fig = _add_admin_bands(fig)
            st.plotly_chart(fig, width="stretch")

        with dt2:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=det_s["fiscal_year"], y=det_s["book_ins"],
                name="Annual Book-ins", marker_color="#8e44ad", opacity=0.8,
                hovertemplate="FY%{x} — %{y:,} book-ins<extra></extra>"))
            if "avg_length_of_stay_days" in det_s.columns:
                los_s = det_s.dropna(subset=["avg_length_of_stay_days"])
                fig2.add_trace(go.Scatter(
                    x=los_s["fiscal_year"], y=los_s["avg_length_of_stay_days"],
                    name="Avg LOS (days, right)", mode="lines+markers",
                    line=dict(color="#e67e22", width=2), yaxis="y2",
                    hovertemplate="FY%{x} — %{y:.1f} days avg<extra></extra>"))
                fig2.update_layout(
                    yaxis2=dict(title="Avg LOS (days)", overlaying="y",
                                side="right", showgrid=False))
            fig2.update_layout(
                yaxis=dict(title="Book-ins", tickformat=","),
                legend=dict(orientation="h", y=1.1),
                hovermode="x unified", height=400, margin=dict(t=60, b=40))
            fig2 = _add_admin_bands(fig2)
            st.plotly_chart(fig2, width="stretch")

        with dt3:
            if det_fac_df is None or det_fac_df.empty:
                st.info("Facility type data not available.")
            else:
                if "facility_type" in det_fac_df.columns and "pct_of_pop" in det_fac_df.columns:
                    fig3 = px.pie(det_fac_df, names="facility_type", values="pct_of_pop",
                        title="Detention Population by Facility Type",
                        color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
                    fig3.update_layout(height=380, margin=dict(t=40, b=20))
                    st.plotly_chart(fig3, width="stretch")
                from utils import clean_dataframe_columns
                st.dataframe(clean_dataframe_columns(det_fac_df), width="stretch", height=350, hide_index=True)

        csv_download_button(det_time_df, "relief_docket_detention.csv", key="det_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: REMOVALS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rem:
    st.subheader("Removal Orders & Departures")
    st.markdown(
        "Removal from the U.S. can happen through multiple legal pathways. "
        "This section tracks the type and volume of removal outcomes."
    )
    if rem_df is None or rem_df.empty:
        no_data_banner()
    else:
        rem_s = rem_df.sort_values("fiscal_year")
        lr = rem_s.iloc[-1]
        pr_rem = rem_s.iloc[-2] if len(rem_s) > 1 else lr
        total_rem = rem_s[rem_s["removal_type"] == "Ordered Removed (IJ)"]["count"].sum() if "removal_type" in rem_s.columns else rem_s["count"].sum()

        rc1, rc2, rc3 = st.columns(3)
        latest_total = rem_s[rem_s["fiscal_year"] == rem_s["fiscal_year"].max()]["count"].sum()
        rc1.metric(f"Total Removal Events (FY{int(rem_s['fiscal_year'].max())})",
                   format_num(int(latest_total)))
        if "removal_type" in rem_df.columns:
            types_this_yr = rem_df[rem_df["fiscal_year"] == rem_df["fiscal_year"].max()]
            top_type = types_this_yr.nlargest(1, "count")
            if not top_type.empty:
                rc2.metric("Largest Removal Type",
                           TYPE_LABELS.get(top_type.iloc[0]["removal_type"],
                                           top_type.iloc[0]["removal_type"]),
                           format_num(top_type.iloc[0]["count"]))
        if rem_nat_df is not None and not rem_nat_df.empty:
            top_nat = rem_nat_df.nlargest(1, "total_removals")
            rc3.metric("Top Nationality", top_nat.iloc[0].get("nat_code", "—"),
                       format_num(top_nat.iloc[0]["total_removals"]))

        rt1, rt2, rt3 = st.tabs(["📊 By Type", "📈 Composition Over Time", "🌍 By Nationality"])

        with rt1:
            if "removal_type" in rem_df.columns:
                yr_max = int(rem_df["fiscal_year"].max())
                yr_min = int(rem_df["fiscal_year"].min())
                fig = go.Figure()
                for rtype in rem_df["removal_type"].dropna().unique():
                    sub = rem_df[rem_df["removal_type"] == rtype].sort_values("fiscal_year")
                    fig.add_trace(go.Bar(
                        x=sub["fiscal_year"], y=sub["count"],
                        name=TYPE_LABELS.get(rtype, rtype),
                        marker_color=TYPE_COLORS.get(rtype, "#95a5a6"),
                        hovertemplate=f"<b>{TYPE_LABELS.get(rtype, rtype)}</b><br>FY%{{x}}: %{{y:,}}<extra></extra>"))
                fig.update_layout(barmode="stack",
                    yaxis=dict(title="Cases", tickformat=","),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    hovermode="x unified", height=420, margin=dict(t=70, b=40))
                fig = _add_admin_bands(fig)
                st.plotly_chart(fig, width="stretch")
            else:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=rem_s["fiscal_year"], y=rem_s["count"],
                    marker_color="#c0392b",
                    hovertemplate="FY%{x} — %{y:,}<extra></extra>"))
                fig.update_layout(yaxis=dict(title="Removals", tickformat=","),
                    height=380, margin=dict(t=20, b=40))
                fig = _add_admin_bands(fig)
                st.plotly_chart(fig, width="stretch")

        with rt2:
            if "removal_type" in rem_df.columns:
                pct_df = rem_df.copy()
                totals = pct_df.groupby("fiscal_year")["count"].transform("sum")
                pct_df["pct"] = pct_df["count"] / totals
                fig2 = go.Figure()
                for rtype in pct_df["removal_type"].dropna().unique():
                    sub = pct_df[pct_df["removal_type"] == rtype].sort_values("fiscal_year")
                    fig2.add_trace(go.Scatter(
                        x=sub["fiscal_year"], y=sub["pct"],
                        name=TYPE_LABELS.get(rtype, rtype),
                        stackgroup="one", mode="none",
                        fillcolor=TYPE_COLORS.get(rtype, "#95a5a6"),
                        hovertemplate=f"FY%{{x}} {TYPE_LABELS.get(rtype, rtype)}: %{{y:.1%}}<extra></extra>"))
                fig2.update_layout(yaxis=dict(title="Share of removals", tickformat=".0%", range=[0, 1]),
                    hovermode="x unified", height=400, margin=dict(t=60, b=40))
                fig2 = _add_admin_bands(fig2)
                st.plotly_chart(fig2, width="stretch")

        with rt3:
            if rem_nat_df is None or rem_nat_df.empty:
                st.info("Nationality breakdown data not available.")
            else:
                top_n = rem_nat_df.nlargest(20, "total_removals").copy()
                fig3 = px.bar(top_n, x="total_removals", y="nat_code", orientation="h",
                    color="total_removals", color_continuous_scale="Reds",
                    text=top_n["total_removals"].map("{:,}".format),
                    labels={"total_removals": "Removals", "nat_code": "Nationality"})
                fig3.update_coloraxes(showscale=False)
                fig3.update_traces(textposition="outside")
                fig3.update_layout(yaxis=dict(autorange="reversed"),
                    height=480, margin=dict(t=20, b=40))
                st.plotly_chart(fig3, width="stretch")
                csv_download_button(rem_nat_df, "relief_docket_removals_by_nationality.csv",
                                    key="rem_nat_dl")
        csv_download_button(rem_df, "relief_docket_removal_orders.csv", key="rem_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: BOND
# ═══════════════════════════════════════════════════════════════════════════════
with tab_bond:
    st.subheader("Bond Hearings")
    st.markdown(
        "An immigration judge can set bond to allow a detained respondent to be released "
        "pending their removal proceedings. DHS sets the initial bond amount; respondents "
        "can request a redetermination hearing."
    )
    if bond_df is None or bond_df.empty:
        no_data_banner()
    else:
        bond_sorted = bond_df.sort_values("fiscal_year")
        lb = bond_sorted.iloc[-1]
        pb = bond_sorted.iloc[-2] if len(bond_sorted) > 1 else lb

        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.metric(f"Bond Hearings (FY{int(lb['fiscal_year'])})",
                   format_num(lb["total_hearings"]),
                   delta=f"{int(lb['total_hearings'] - pb['total_hearings']):+,}",
                   delta_color="off")
        bc2.metric("Grant Rate", format_pct(lb["grant_rate"]),
                   delta=f"{(lb['grant_rate'] - pb['grant_rate'])*100:+.1f}pp")
        bc3.metric("Median Bond Amount",
                   f"${lb['median_bond']:,.0f}",
                   delta=f"${lb['median_bond'] - pb['median_bond']:+,.0f}",
                   delta_color="inverse")
        if "detention_rate_post" in lb:
            bc4.metric("Detention Rate Post-Hearing", format_pct(lb["detention_rate_post"]))

        bond_yr = st.slider("Fiscal year range",
            min_value=int(bond_df["fiscal_year"].min()),
            max_value=int(bond_df["fiscal_year"].max()),
            value=(2005, int(bond_df["fiscal_year"].max())),
            key="bond_yr_range")
        bond_f = bond_df[bond_df["fiscal_year"].between(bond_yr[0], bond_yr[1])].copy()
        bond_f = bond_f.sort_values("fiscal_year")

        # Chart 1: grant rate trend
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=bond_f["fiscal_year"], y=bond_f["grant_rate"],
            mode="lines+markers", name="Bond Grant Rate",
            line=dict(color="#1e8a50", width=2.5),
            fill="tozeroy", fillcolor="rgba(30,138,80,0.12)",
            hovertemplate="FY%{x} — Grant Rate: %{y:.1%}<extra></extra>"))
        fig1.update_layout(
            yaxis=dict(title="Grant Rate", tickformat=".0%"),
            height=320, margin=dict(t=40, b=40))
        fig1 = _add_admin_bands(fig1)

        # Chart 2: median bond
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=bond_f["fiscal_year"], y=bond_f["median_bond"],
            mode="lines+markers", name="Median Bond Amount",
            line=dict(color="#c0392b", width=2.5),
            fill="tozeroy", fillcolor="rgba(192,57,43,0.12)",
            hovertemplate="FY%{x} — Median Bond: $%{y:,.0f}<extra></extra>"))
        fig2.update_layout(
            yaxis=dict(title="Median Bond ($)", tickprefix="$", tickformat=","),
            height=320, margin=dict(t=40, b=40))
        fig2 = _add_admin_bands(fig2)

        col_g, col_m = st.columns(2)
        with col_g:
            st.caption("Bond Grant Rate by Year")
            st.plotly_chart(fig1, width="stretch")
        with col_m:
            st.caption("Median Bond Amount by Year")
            st.plotly_chart(fig2, width="stretch")

        # Chart 3: stacked granted/denied
        if "granted" in bond_f.columns and "denied" in bond_f.columns:
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=bond_f["fiscal_year"], y=bond_f["granted"],
                name="Bond Granted", marker_color="#1e8a50", opacity=0.85,
                hovertemplate="FY%{x} — Granted: %{y:,}<extra></extra>"))
            fig3.add_trace(go.Bar(
                x=bond_f["fiscal_year"], y=bond_f["denied"],
                name="Bond Denied", marker_color="#c0392b", opacity=0.85,
                hovertemplate="FY%{x} — Denied: %{y:,}<extra></extra>"))
            fig3.update_layout(barmode="stack",
                yaxis=dict(title="Bond Hearings", tickformat=","),
                legend=dict(orientation="h", y=1.1),
                hovermode="x unified", height=360, margin=dict(t=60, b=40))
            fig3 = _add_admin_bands(fig3)
            st.plotly_chart(fig3, width="stretch")

        if "detention_rate_post" in bond_f.columns:
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(
                x=bond_f["fiscal_year"], y=bond_f["detention_rate_post"],
                mode="lines+markers", name="Detention Rate (post-hearing)",
                line=dict(color="#8e44ad", width=2.5),
                hovertemplate="FY%{x} — Detained: %{y:.1%}<extra></extra>"))
            fig4.update_layout(
                yaxis=dict(title="Detention Rate", tickformat=".0%"),
                height=280, margin=dict(t=40, b=40))
            fig4 = _add_admin_bands(fig4)
            st.plotly_chart(fig4, width="stretch")

        with st.expander("Why bond matters"):
            st.markdown("""
**Bond is often the most consequential single hearing in an immigration case.**

- Respondents who are **detained** are ~3× less likely to appear with counsel
- Detained dockets move faster, leaving less time to prepare a case
- High bond amounts ($10,000–$25,000+) are functionally equivalent to no bond for many families
- Bond amounts have increased significantly under enforcement-focused administrations

**The legal standard:** Under INA §236(a), the DHS can detain or set bond. An IJ reviews
whether the respondent is a **danger to the community** or **flight risk**. Mandatory
detention applies to certain criminal grounds under INA §236(c), with no bond hearing.
            """)

        csv_download_button(bond_df, "relief_docket_bond.csv", key="bond_dl")

add_gavel_glimpse_footer()
