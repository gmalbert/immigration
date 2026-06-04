import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from utils import add_sidebar_logo
from utils.today_in_history import get_today_in_history, index_exists

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# ΓöÇΓöÇ App-wide config ΓÇö called ONCE here; sub-pages must NOT call set_page_config ΓöÇΓöÇ
st.set_page_config(
    page_title="Supreme Scrutiny",
    page_icon="≡ƒÅ¢∩╕Å",
    layout="wide",
    initial_sidebar_state="expanded",
)


def home_page():
    _logo_path = os.path.join(_REPO_ROOT, "data_files", "logo.png")
    add_sidebar_logo(hide_sidebar_logo=True)

    # ΓöÇΓöÇ Hero ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    _hero_img, _hero_text = st.columns([2, 6], vertical_alignment="center")
    with _hero_img:
        if os.path.exists(_logo_path):
            st.image(_logo_path, width=220)
        else:
            st.markdown("### ≡ƒÅ¢∩╕Å")
    with _hero_text:
        st.title("Supreme Scrutiny")
        # st.markdown(
        #     "The complete guide to U.S. Supreme Court decisions ΓÇö "
        #     "**8,251 cases spanning 71 terms**, fully searchable and locally cached."
        # )

    # ΓöÇΓöÇ Today in SCOTUS History ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    if index_exists():
        from datetime import date as _date
        _img_path = os.path.join(_REPO_ROOT, "data_files", "on_this_day.png")
        today_case = get_today_in_history()
        if today_case:
            event_type = "decided" if today_case.get("date_field") == "decided_on" else "argued"
            with st.container(border=True):
                col_img, col_text, col_btn = st.columns([1, 5, 1])
                with col_img:
                    if os.path.exists(_img_path):
                        st.image(_img_path, width=90)
                    else:
                        st.markdown("≡ƒôà")
                with col_text:
                    st.markdown("#### On This Day in SCOTUS History")
                    st.markdown(
                        f"**{_date.today().strftime('%B')} {_date.today().day}** &nbsp;┬╖&nbsp; "
                        f"*{today_case['name']}* was **{event_type}** "
                        f"({today_case['term']} term)"
                    )
                with col_btn:
                    st.markdown("&nbsp;")
                    if st.button(
                        "Explore ΓåÆ",
                        key="today_btn",
                        type="primary",
                        width="stretch",
                    ):
                        st.session_state["_today_case_query"] = today_case["name"]
                        st.switch_page("pages/1_Cases.py")

    # ΓöÇΓöÇ Case Search ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    st.markdown("---")
    with st.container(border=True):
        st.markdown("#### ≡ƒöì Find Cases by Description")
        st.caption("Describe a legal situation in plain language and find the most relevant Supreme Court cases.")
        _home_query = st.text_area(
            "Describe a legal situation",
            label_visibility="collapsed",
            placeholder=(
                "e.g. police searched a suspect's cell phone without a warrant\n"
                "e.g. government required a license to display a religious symbol\n"
                "e.g. employer fired a worker for union organizing activity"
            ),
            height=100,
            key="_home_desc_input",
        )
        _home_col1, _home_col2 = st.columns([1, 5])
        with _home_col1:
            _home_n = st.slider("Results", 3, 20, 15, key="_home_desc_n")
        with _home_col2:
            _home_btn = st.button("≡ƒöì Find Cases", type="primary", key="_home_desc_btn", width="content")
        if _home_btn and _home_query and len(_home_query.strip()) >= 10:
            st.session_state["desc_query"] = _home_query
            st.session_state["_home_desc_n_val"] = _home_n
            st.session_state["_home_trigger_search"] = True
            st.switch_page("pages/1_Cases.py")
        elif _home_btn and _home_query:
            st.warning("Please enter at least 10 characters.")

    st.markdown("---")

    # ΓöÇΓöÇ Navigation Cards ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    st.markdown("### Explore the Court")

    _NAV = [
        (
            "ΓÜû∩╕Å", "Cases",
            "Search and browse 8,000+ cases by name, term, keyword, or plain-language description.",
            "pages/1_Cases.py",
        ),
        (
            "≡ƒæÑ", "Justices & Advocates",
            "Voting records, ideology drift over time, agreement matrices, and advocate win rates.",
            "pages/People.py",
        ),
        (
            "≡ƒö«", "Predictions",
            "ML-powered outcome predictions, cert grant estimator, model card, and docket watch.",
            "pages/9_Predictions.py",
        ),
        (
            "≡ƒôè", "Analytics",
            "Term-by-term statistics, issue-area breakdowns, reversal rates, and voting trends.",
            "pages/Analysis.py",
        ),

    ]

    for row_start in range(0, len(_NAV), 2):
        row_items = _NAV[row_start : row_start + 2]
        cols = st.columns(2)
        for col, (icon, title, desc, page_path) in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    st.markdown(f"#### {icon} {title}")
                    st.caption(desc)
                    if st.button(
                        f"Open {title} ΓåÆ",
                        key=f"nav_{title.replace(' ', '_').replace('&', 'and')}",
                        width="stretch",
                    ):
                        st.switch_page(page_path)

    # ΓöÇΓöÇ About ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    st.markdown("---")
    with st.expander("Γä╣∩╕Å About Supreme Scrutiny"):
        st.markdown("""
**Supreme Scrutiny** is an open-source data visualization and analysis tool for U.S. Supreme Court history.

**Data sources and Coverage:**
- [Oyez](https://www.oyez.org) ΓÇö case metadata, oral argument audio, and justice records
- **Terms:** 1955 ΓÇô 2025 (71 terms)
- **Cases:** 8,251 with complete metadata; 8,238 with full case details
- **Voting data:** Included for cases with recorded decisions

        """)

# ΓöÇΓöÇ Navigation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
pg = st.navigation(
    {
        "": [
            st.Page(home_page,                     title="Home",              icon="≡ƒÅá", default=True),
        ],
        "Cases": [
            st.Page("pages/1_Cases.py",            title="Cases",             icon="ΓÜû∩╕Å"),
        ],
        "People": [
            st.Page("pages/People.py",             title="Justices & Advocates", icon="≡ƒæÑ"),
        ],
        "History & Courts": [
            st.Page("pages/History.py",            title="Court History",     icon="≡ƒÅ¢∩╕Å"),
            st.Page("pages/13_Historical_Data.py", title="Full Timeline",     icon="≡ƒô£"),
            st.Page("pages/5_Circuit_Courts.py",   title="Circuit Courts",    icon="≡ƒù║∩╕Å"),
            st.Page("pages/12_Geography.py",       title="Geography",         icon="≡ƒîÄ"),
        ],
        "Analysis": [
            st.Page("pages/Analysis.py",           title="Analytics",         icon="≡ƒôè"),
            st.Page("pages/Topics.py",             title="Topics & Networks", icon="≡ƒôÜ"),
            st.Page("pages/8_Presidential_Legacy.py", title="Presidential Legacy", icon="≡ƒÅà"),
            st.Page("pages/10_Research.py",        title="Research",          icon="≡ƒö¼"),
        ],
        "Predictions": [
            st.Page("pages/9_Predictions.py",      title="Predictions",       icon="≡ƒö«"),
        ],
    }
)
pg.run()

