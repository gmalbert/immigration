"""
Relief Docket — Immigration Court Analytics
Entry point: multi-page navigation via st.navigation()
"""

import streamlit as st
from pathlib import Path
import base64

# Must be first Streamlit command
st.set_page_config(
    page_title="Relief Docket | Immigration Court Analytics",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils import add_sidebar
from utils.data_loader import has_any_data, get_pipeline_status
from footer import add_gavel_glimpse_footer

_ROOT = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH METADATA
# ══════════════════════════════════════════════════════════════════════════════

_PAGE_INDEX = [
    {
        "title": "Judges",
        "icon": "👨‍⚖️",
        "path": "pages/F_Judges.py",
        "desc": "Grant rates, removal rates, side-by-side comparison, refugee roulette",
        "keywords": "judge immigration judicial grant rate removal asylum statistics bias refugee roulette outlier",
    },
    {
        "title": "Courts & Geography",
        "icon": "🏛️",
        "path": "pages/B_Courts.py",
        "desc": "Court profiles, caseload maps, origin maps, circuit comparison",
        "keywords": "court immigration geographic map city state circuit location regional backlog",
    },
    {
        "title": "Case Processing",
        "icon": "📊",
        "path": "pages/C_Case_Processing.py",
        "desc": "Case outcomes, backlog growth, processing time by court and detention",
        "keywords": "case outcome backlog processing time age granted removed voluntary departure detained",
    },
    {
        "title": "Respondents",
        "icon": "👥",
        "path": "pages/D_Respondents.py",
        "desc": "Countries of origin, attorney representation gap, unaccompanied children",
        "keywords": "nationality country representation attorney pro se unaccompanied children UAC Mexico Guatemala Honduras",
    },
    {
        "title": "Enforcement",
        "icon": "🔒",
        "path": "pages/E_Enforcement.py",
        "desc": "In absentia orders, ICE detention, removal pathways, bond hearings",
        "keywords": "absentia detention removal deportation ICE bond hearing expedited credible fear",
    },
    {
        "title": "Policy & Appeals",
        "icon": "🏛️",
        "path": "pages/A_Policy_Appeals.py",
        "desc": "Policy shifts across administrations, BIA outcomes, circuit reversals",
        "keywords": "policy administration BIA appeals circuit reversal presidential political trends closure termination",
    },
    {
        "title": "Data Quality",
        "icon": "🔍",
        "path": "pages/G_Data_Quality.py",
        "desc": "Known EOIR data quality issues — disappearing records, schema changes",
        "keywords": "data quality TRAC missing disappearing records FOIA EOIR database schema validation",
    },
]


def _search_pages(query: str):
    """Return page metadata matching the search query."""
    q_lower = query.lower()
    matches = []
    for pg in _PAGE_INDEX:
        combined = f"{pg['title']} {pg['desc']} {pg['keywords']}".lower()
        if q_lower in combined:
            matches.append(pg)
    return matches


# ══════════════════════════════════════════════════════════════════════════════
# HOME PAGE
# ══════════════════════════════════════════════════════════════════════════════


def home_page():
    add_sidebar("home")

    # Load logo as base64 for HTML embedding with forced transparency
    logo_path = Path(__file__).parent / "data_files" / "logo_transparent.png"
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()

    # ── Logo + Description (single column) ───────────────────────────────────
    st.markdown(
        f"""
        <div style="text-align: center; margin-bottom: 1.5rem;">
            <img src="data:image/png;base64,{logo_b64}" width="300" 
                 style="background: transparent; display: block; margin: 0 auto; border: none;" />
            <p style="font-size: 1.15rem; color: #4a5568; margin-top: 1rem; max-width: 720px; margin-left: auto; margin-right: auto;">
                Interactive analytics for U.S. immigration courts — judge profiles,
                court statistics, nationality outcomes, and policy trend analysis
                built from the EOIR CASE database.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Data status ───────────────────────────────────────────────────────────
    status = get_pipeline_status()
    if status.get("seed_mode"):
        st.info(
            "**Displaying aggregate statistics** — seed data from documented EOIR sources. "
            "For individual judge and case-level analytics, run the full pipeline "
            "(see **Data Quality** page for instructions).",
            icon="ℹ️",
        )
    elif not has_any_data():
        st.warning(
            "**No data loaded.** Run `python scripts/seed_data.py` then refresh this page.",
            icon="⚙️",
        )

    # ── Key metrics row ───────────────────────────────────────────────────────
    if has_any_data():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Pending Cases (2026)", "3.3M+", delta="+24% vs 2024", delta_color="inverse")
        with col2:
            st.metric("National Asylum Grant Rate", "~28%", delta="-4pp vs 2023")
        with col3:
            st.metric("Pro Se Rate", "~59%", help="Share of pending cases with no attorney")
        with col4:
            st.metric("Active Courts", "70+", help="Immigration courts nationwide")

        st.markdown("---")

    # ── Feature cards ─────────────────────────────────────────────────────────
    st.markdown("### Explore")

    query = st.text_input(
        "Search pages",
        placeholder="🔍 Search pages — try: asylum, judge, Mexico, detention, circuit, backlog…",
        label_visibility="collapsed",
        key="home_search",
    )
    if query.strip():
        matches = _search_pages(query.strip())
        if matches:
            st.caption(
                f"**{len(matches)} page result{'s' if len(matches) != 1 else ''}** "
                "for your search — scroll down to browse all pages"
            )
            for row_i in range(0, min(len(matches), 8), 4):
                row_pages = matches[row_i : row_i + 4]
                _cols = st.columns(4)
                for j, (col, pg) in enumerate(zip(_cols, row_pages)):
                    with col:
                        with st.container(border=True):
                            st.markdown(f"#### {pg['icon']} {pg['title']}")
                            st.caption(pg["desc"])
                            if st.button(
                                f"Go → {pg['title']}",
                                key=f"sr_{row_i + j}",
                                width="stretch",
                            ):
                                st.switch_page(pg["path"])
        else:
            st.info(
                "No pages matched. Try: judge, asylum, Mexico, detention, "
                "circuit, backlog, UAC, appeals, bond…"
            )
        st.markdown("---")

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)

    with r1c1:
        with st.container(border=True):
            st.markdown("#### 👨‍⚖️ Judges")
            st.caption("Grant rates, removal rates, side-by-side comparison, and refugee roulette analysis.")
            if st.button("View Judges", key="nav_judges", type="primary", width="stretch"):
                st.switch_page("pages/F_Judges.py")

    with r1c2:
        with st.container(border=True):
            st.markdown("#### 🏛️ Courts & Geography")
            st.caption("Court profiles, caseload maps, origin country choropleth, and circuit comparison.")
            if st.button("View Courts", key="nav_courts", type="primary", width="stretch"):
                st.switch_page("pages/B_Courts.py")

    with r1c3:
        with st.container(border=True):
            st.markdown("#### 📊 Case Processing")
            st.caption("Case outcomes, backlog growth, and processing time by court and detention status.")
            if st.button("View Case Processing", key="nav_cp", type="primary", width="stretch"):
                st.switch_page("pages/C_Case_Processing.py")

    with r1c4:
        with st.container(border=True):
            st.markdown("#### 👥 Respondents")
            st.caption("Countries of origin, attorney representation gap, and unaccompanied children trends.")
            if st.button("View Respondents", key="nav_resp", type="primary", width="stretch"):
                st.switch_page("pages/D_Respondents.py")

    # ── About the data ────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("About the data", expanded=False):
        st.markdown("""
        **Relief Docket** is built on the **EOIR CASE database** — the Executive Office for
        Immigration Review's internal case management system, released monthly under FOIA
        (justice.gov/eoir/foia-library-0).

        The database contains over **164 million rows across 97 tables**, covering every
        immigration court proceeding since the 1970s. It is updated monthly and is
        freely available with no API key.

        **What this site tracks:**
        - Immigration court cases: outcomes, hearing dates, case ages
        - Judge-level analytics: grant rates, removal rates, in absentia rates
        - Court profiles: backlog, wait times, representation rates
        - Nationality breakdowns: asylum outcomes for 200+ nationalities
        - Policy trends: administrative closure, termination, and in absentia rates
          across presidential administrations

        **What is NOT in this data:**
        - Expedited removal cases (handled by DHS/ICE without an immigration judge)
        - USCIS affirmative asylum decisions
        - Immigration court written opinions/reasoning
        - ICE arrest and detention data (separate system, not linkable)

        **Data quality:** EOIR data has well-documented quality issues, including a
        2019–2022 period of disappearing records documented by TRAC at Syracuse University.
        This pipeline archives every monthly release and preserves records that disappear
        from new releases. See the **Data Quality** page for full details.

        *Sources: EOIR FOIA Library · TRAC Immigration (tracreports.org) · Vera Institute ·
        Deportation Data Project · Congressional Research Service*
        """)

    # ── Footer ─────────────────────────────────────────────────────────────────
    add_gavel_glimpse_footer()


# ── Navigation ────────────────────────────────────────────────────────────────
pages = st.navigation(
    pages=[
        st.Page(home_page,                     title="Home",              icon="🏠", default=True),
        st.Page("pages/F_Judges.py",           title="Judges",            icon="👨‍⚖️"),
        st.Page("pages/B_Courts.py",           title="Courts & Geography",icon="🏛️"),
        st.Page("pages/C_Case_Processing.py",  title="Case Processing",   icon="📊"),
        st.Page("pages/D_Respondents.py",      title="Respondents",       icon="👥"),
        st.Page("pages/E_Enforcement.py",      title="Enforcement",       icon="🔒"),
        st.Page("pages/A_Policy_Appeals.py",   title="Policy & Appeals",  icon="🏛️"),
        st.Page("pages/G_Data_Quality.py",     title="Data Quality",      icon="🔍"),
    ]
)
pages.run()
