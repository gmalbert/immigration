"""
pages/D_Respondents.py — Respondents (merged)

Tab 1: Nationalities — case volumes and grant rates by country of origin
Tab 2: Representation — attorney representation gap trends
Tab 3: UAC — unaccompanied children trends and outcomes
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import add_sidebar, no_data_banner, format_num, format_pct, csv_download_button
from utils.data_loader import (
    load_nationality_metrics, load_nationality_lookup,
    load_representation_gap, load_uac_metrics, load_uac_origin,
    get_pipeline_status,
)
from utils.charts import nationality_volume_chart, representation_gap_chart, _add_admin_bands
from footer import add_gavel_glimpse_footer

add_sidebar("respondents")

st.title("👥 Respondents")
st.caption(
    "Who appears in U.S. immigration courts: countries of origin, attorney representation, "
    "and outcomes for unaccompanied children."
)

status = get_pipeline_status()
if status.get("seed_mode"):
    st.warning(
        "**Seed mode** — statistics sourced from EOIR Yearbooks, TRAC Immigration, "
        "ORR, and American Immigration Council data.",
        icon="⚠️",
    )

nat_df   = load_nationality_metrics()
nat_look  = load_nationality_lookup()
rep_df   = load_representation_gap()
uac_df   = load_uac_metrics()
uac_orig = load_uac_origin()

tab_nat, tab_rep, tab_uac = st.tabs(["🌍 Nationalities", "👤 Representation", "👧 UAC"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: NATIONALITIES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_nat:
    st.subheader("Case Volume by Nationality")
    st.markdown(
        "Countries of origin for all immigration court cases. "
        "Numbers reflect docketed cases, not necessarily final population estimates."
    )

    if nat_df is None or nat_df.empty:
        no_data_banner()
    else:
        n1, n2, n3 = st.columns(3)
        n1.metric("Total Nationalities", format_num(len(nat_df)))
        n2.metric("Total Cases (all nationalities)", format_num(nat_df["case_count"].sum()))
        top = nat_df.nlargest(1, "case_count")
        n3.metric("Largest Origin Country",
                  f"{top.iloc[0]['nat_code']} — {format_num(top.iloc[0]['case_count'])}")

        fig = nationality_volume_chart(nat_df)
        if fig:
            st.plotly_chart(fig, width='stretch')

        nt1, nt2, nt3, nt4 = st.tabs(["🔍 Search by Country", "📈 Highest Grant Rates",
                                       "📉 Lowest Grant Rates", "📋 All Data"])

        with nt1:
            nat_search = st.text_input("Type a country code or name:", key="nat_search",
                                        placeholder="e.g. MEX, GTM, Honduras")
            if nat_search:
                mask = nat_df["nat_code"].str.contains(nat_search.upper(), na=False)
                if nat_look is not None:
                    name_mask = nat_df["nat_code"].map(
                        lambda c: nat_search.lower() in nat_look.get(c, "").lower()
                    )
                    mask = mask | name_mask
                results = nat_df[mask].copy()
                if results.empty:
                    st.info(f"No country found matching '{nat_search}'.")
                else:
                    for _, row in results.iterrows():
                        label = nat_look.get(row["nat_code"], row["nat_code"]) if nat_look else row["nat_code"]
                        st.markdown(f"### {label} ({row['nat_code']})")
                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("Total Cases", format_num(row["case_count"]))
                        mc2.metric("Asylum Grant Rate", format_pct(row["asylum_grant_rate"]))
                        mc3.metric("Represented", format_pct(row["representation_rate"]))

        with nt2:
            st.markdown("**Top 20 nationalities by asylum grant rate** (min. 200 cases)")
            top20 = nat_df[nat_df["case_count"] >= 200].nlargest(20, "asylum_grant_rate").copy()
            top20["Nationality"] = top20["nat_code"].map(
                lambda c: nat_look.get(c, c) if nat_look else c)
            top20["Grant Rate"] = top20["asylum_grant_rate"].map("{:.1%}".format)
            top20["Cases"] = top20["case_count"].map("{:,}".format)
            top20["Represented"] = top20["representation_rate"].map("{:.1%}".format)
            fig_top = px.bar(top20, x="asylum_grant_rate", y="Nationality",
                orientation="h",
                color="asylum_grant_rate",
                color_continuous_scale="Greens",
                text=top20["asylum_grant_rate"].map("{:.1%}".format),
                labels={"asylum_grant_rate": "Grant Rate"})
            fig_top.update_coloraxes(showscale=False)
            fig_top.update_traces(textposition="outside")
            fig_top.update_layout(yaxis=dict(autorange="reversed"),
                height=520, margin=dict(t=20, b=40))
            st.plotly_chart(fig_top, width='stretch')

        with nt3:
            st.markdown("**Bottom 20 nationalities by asylum grant rate** (min. 200 cases)")
            bot20 = nat_df[nat_df["case_count"] >= 200].nsmallest(20, "asylum_grant_rate").copy()
            bot20["Nationality"] = bot20["nat_code"].map(
                lambda c: nat_look.get(c, c) if nat_look else c)
            fig_bot = px.bar(bot20, x="asylum_grant_rate", y="Nationality",
                orientation="h",
                color="asylum_grant_rate",
                color_continuous_scale="Reds_r",
                text=bot20["asylum_grant_rate"].map("{:.1%}".format),
                labels={"asylum_grant_rate": "Grant Rate"})
            fig_bot.update_coloraxes(showscale=False)
            fig_bot.update_traces(textposition="outside")
            fig_bot.update_layout(yaxis=dict(autorange="reversed"),
                height=520, margin=dict(t=20, b=40))
            st.plotly_chart(fig_bot, width='stretch')

        with nt4:
            all_nat = pd.DataFrame({
                "Nationality Code": nat_df["nat_code"],
                "Country Name": nat_df["nat_code"].map(
                    lambda c: nat_look.get(c, c) if nat_look else c
                ),
                "Cases": nat_df["case_count"].map("{:,}".format),
                "Grant Rate": nat_df["asylum_grant_rate"].map("{:.1%}".format),
                "Represented": nat_df["representation_rate"].map("{:.1%}".format),
            })
            st.dataframe(all_nat, width='stretch', height=500, hide_index=True)

        csv_download_button(nat_df, "relief_docket_nationalities.csv", key="nat_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: REPRESENTATION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rep:
    st.subheader("Attorney Representation Gap")
    st.markdown(
        "Access to legal representation is the single strongest predictor of case outcome. "
        "This section tracks how representation rates have changed over time."
    )

    if rep_df is None or rep_df.empty:
        no_data_banner()
    else:
        latest_rep = rep_df.sort_values("fiscal_year").iloc[-1]
        prev_rep   = rep_df.sort_values("fiscal_year").iloc[-2] if len(rep_df) > 1 else latest_rep

        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric(f"Represented Rate (FY{int(latest_rep['fiscal_year'])})",
                   format_pct(latest_rep["representation_rate"]),
                   delta=f"{(latest_rep['representation_rate'] - prev_rep['representation_rate'])*100:+.1f}pp")
        rc2.metric("Pro Se Rate", format_pct(1 - latest_rep["representation_rate"]))
        if "detained_rep_rate" in latest_rep:
            rc3.metric("Detained Represented", format_pct(latest_rep["detained_rep_rate"]))
        if "prose_grant_rate" in latest_rep and "represented_grant_rate" in latest_rep:
            multiplier = (latest_rep["represented_grant_rate"] / latest_rep["prose_grant_rate"]
                          if latest_rep["prose_grant_rate"] else 1)
            rc4.metric("Represented vs. Pro Se Grant Rate", f"{multiplier:.1f}×")

        rep_yr = st.slider("Fiscal Year Range",
            min_value=int(rep_df["fiscal_year"].min()),
            max_value=int(rep_df["fiscal_year"].max()),
            value=(2000, int(rep_df["fiscal_year"].max())),
            key="rep_year_range")
        rep_filt = rep_df[rep_df["fiscal_year"].between(rep_yr[0], rep_yr[1])].copy()

        fig_rep = representation_gap_chart(rep_filt)
        if fig_rep:
            st.plotly_chart(fig_rep, width='stretch')

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("#### Why representation matters")
            st.markdown("""
- **Grant rate gap:** Represented respondents are **5× more likely** to receive relief
- **Procedural advantage:** Attorneys identify applicable relief categories
- **Appeals:** Represented respondents appeal at much higher rates
- **Detention:** Detained individuals struggle to find counsel; some courts see 80%+ pro se rates
            """)
        with col_r:
            st.markdown("#### Barriers to representation")
            st.markdown("""
- **Cost:** Private immigration attorneys typically charge $1,500–$8,000+
- **Geographic access:** Many courts are in rural detention centers with few nearby attorneys
- **Language barriers:** Need for same-language counsel reduces the pool
- **No right to appointed counsel:** Unlike criminal proceedings, no 6th Amendment guarantee
- **Detention speed:** Detained dockets move faster, limiting time to find counsel
            """)

        csv_download_button(rep_df, "relief_docket_representation_gap.csv", key="rep_dl")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: UAC
# ═══════════════════════════════════════════════════════════════════════════════
with tab_uac:
    st.subheader("Unaccompanied Children (UAC)")
    st.markdown(
        "Children who arrive at the U.S. border without a parent or legal guardian are "
        "classified as Unaccompanied Alien Children (UAC) and go through a distinct process "
        "governed by the Trafficking Victims Protection Reauthorization Act (TVPRA) of 2008."
    )

    if uac_df is None or uac_df.empty:
        no_data_banner()
    else:
        uac_sorted = uac_df.sort_values("fiscal_year")
        lu = uac_sorted.iloc[-1]
        pu = uac_sorted.iloc[-2] if len(uac_sorted) > 1 else lu

        uc1, uc2, uc3 = st.columns(3)
        uc1.metric(f"UAC Apprehensions (FY{int(lu['fiscal_year'])})",
                   format_num(lu["apprehensions"]),
                   delta=f"{int(lu['apprehensions'] - pu['apprehensions']):+,}",
                   delta_color="off")
        uc2.metric("UAC With Representation",
                   format_pct(lu.get("representation_rate", 0)))
        if "pending_cases" in lu:
            uc3.metric("UAC Pending Cases", format_num(lu["pending_cases"]))

        uac_yr = st.slider("Fiscal Year Range",
            min_value=int(uac_df["fiscal_year"].min()),
            max_value=int(uac_df["fiscal_year"].max()),
            value=(2010, int(uac_df["fiscal_year"].max())),
            key="uac_yr_range")
        uac_f = uac_df[uac_df["fiscal_year"].between(uac_yr[0], uac_yr[1])].copy()

        ut1, ut2, ut3 = st.tabs(["📈 Arrival Trends", "🌍 Country of Origin", "📋 Outcomes"])

        with ut1:
            fig_uac = go.Figure()
            fig_uac.add_trace(go.Bar(
                x=uac_f["fiscal_year"], y=uac_f["apprehensions"],
                name="Apprehensions", marker_color="#2980b9", opacity=0.85,
                hovertemplate="FY%{x} — %{y:,} apprehensions<extra></extra>"))
            if "pending_cases" in uac_f.columns:
                fig_uac.add_trace(go.Scatter(
                    x=uac_f["fiscal_year"], y=uac_f["pending_cases"],
                    name="Pending Court Cases", mode="lines+markers",
                    line=dict(color="#c0392b", width=2),
                    yaxis="y2",
                    hovertemplate="FY%{x} — %{y:,} pending<extra></extra>"))
                fig_uac.update_layout(yaxis2=dict(
                    title="Pending Cases", overlaying="y", side="right", showgrid=False))
            fig_uac.update_layout(
                yaxis=dict(title="Apprehensions", tickformat=","),
                hovermode="x unified",
                legend=dict(orientation="h", y=1.1),
                height=400, margin=dict(t=60, b=40))
            fig_uac = _add_admin_bands(fig_uac)
            st.plotly_chart(fig_uac, width="stretch")

            with st.expander("TVPRA protections for UAC"):
                st.markdown("""
The **Trafficking Victims Protection Reauthorization Act (TVPRA, 2008)** created special
protections for unaccompanied children:

- **Non-contiguous countries:** Children from countries other than Mexico or Canada may not be
  immediately returned; they are transferred to ORR custody within 72 hours.
- **Asylum access:** UAC can apply for asylum affirmatively or defensively.
- **Initial jurisdiction:** USCIS has initial jurisdiction over UAC asylum applications.
- **Legal representation:** TVPRA authorizes, but does not require, legal representation programs.

**Key court rulings:** *Flores v. Reno* (1997) consent decree set minimum detention standards;
*JEFM v. Lynch* (2015) sought right to counsel (denied at circuit level).
                """)

        with ut2:
            if uac_orig is None or uac_orig.empty:
                st.info("UAC origin data not available.")
            else:
                era_options = uac_orig["era"].dropna().unique().tolist() if "era" in uac_orig.columns else []
                if era_options:
                    era_choice = st.radio("Select era", sorted(era_options),
                                           horizontal=True, key="uac_origin_era")
                    orig_f = uac_orig[uac_orig["era"] == era_choice].copy()
                else:
                    orig_f = uac_orig.copy()
                fig_orig = px.bar(
                    orig_f.sort_values("count", ascending=False).head(15),
                    x="nat_code", y="count",
                    labels={"nat_code": "Nationality", "count": "UAC Cases"},
                    color="count",
                    color_continuous_scale="Blues",
                    text=orig_f.sort_values("count", ascending=False).head(15)["count"].map("{:,}".format),
                )
                fig_orig.update_coloraxes(showscale=False)
                fig_orig.update_traces(textposition="outside")
                fig_orig.update_layout(height=380, margin=dict(t=20, b=40))
                st.plotly_chart(fig_orig, width="stretch")

        with ut3:
            if "grant_rate" in uac_f.columns:
                fig_out = go.Figure()
                fig_out.add_trace(go.Scatter(
                    x=uac_f["fiscal_year"], y=uac_f["grant_rate"],
                    mode="lines+markers", name="UAC Grant Rate",
                    line=dict(color="#1e8a50", width=2.5),
                    hovertemplate="FY%{x} — %{y:.1%} granted<extra></extra>"))
                if "removal_rate" in uac_f.columns:
                    fig_out.add_trace(go.Scatter(
                        x=uac_f["fiscal_year"], y=uac_f["removal_rate"],
                        mode="lines+markers", name="UAC Removal Rate",
                        line=dict(color="#c0392b", width=2, dash="dash"),
                        hovertemplate="FY%{x} — %{y:.1%} removed<extra></extra>"))
                fig_out.update_layout(
                    yaxis=dict(title="Rate", tickformat=".0%"),
                    hovermode="x unified",
                    legend=dict(orientation="h", y=1.1),
                    height=360, margin=dict(t=60, b=40))
                fig_out = _add_admin_bands(fig_out)
                st.plotly_chart(fig_out, width="stretch")
            else:
                st.info("UAC outcome data not available.")

        csv_download_button(uac_df, "relief_docket_uac.csv", key="uac_dl")

add_gavel_glimpse_footer()
