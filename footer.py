"""
Gavel Glimpse Footer Component

Copy this file to a Streamlit app repository and import it to add consistent
Gavel Glimpse branding and the informational-purpose disclaimer.
"""

GAVEL_GLIMPSE_URL = "http://www.gavel-glimpse.com"
GAVEL_GLIMPSE_LOGO_URL = (
    "https://raw.githubusercontent.com/gmalbert/gavel-glimpse/main/data_files/logo_no_text.png"
)


FOOTER_HTML = f"""
<div style="
    border-top: 1px solid #d8dee8;
    margin-top: 40px;
    padding: 22px 0;
    font-family: Aptos, 'Aptos Display', 'Segoe UI', system-ui, -apple-system, sans-serif;
">
    <div style="
        display: flex;
        align-items: center;
        gap: 14px;
        max-width: 900px;
        margin: 0 auto;
        color: #5c6878;
    ">
        <a href="{GAVEL_GLIMPSE_URL}" target="_blank" rel="noopener noreferrer" style="flex: 0 0 auto;">
            <img src="{GAVEL_GLIMPSE_LOGO_URL}"
                 alt="Gavel Glimpse"
                 style="height: 46px; width: 46px; object-fit: contain; border: none;">
        </a>
        <div style="flex: 1 1 auto;">
            <p style="margin: 0; font-size: 15px; color: #10243d; font-weight: 700;">
                Part of <a href="{GAVEL_GLIMPSE_URL}"
                           target="_blank"
                           rel="noopener noreferrer"
                           style="color: #0f5f73; text-decoration: none; font-weight: 700;">
                    Gavel Glimpse
                </a>
            </p>
            <p style="margin: 5px 0 0 0; font-size: 13px; line-height: 1.5; color: #5c6878;">
                This public legal-data site is created for informational and research purposes only.
                It does not provide legal advice and is not a substitute for consulting a qualified attorney.
            </p>
        </div>
    </div>
</div>
"""


def add_gavel_glimpse_footer():
    """
    Add the Gavel Glimpse footer to a Streamlit app.

    Usage:
        from footer import add_gavel_glimpse_footer

        # At the end of each page
        add_gavel_glimpse_footer()
    """
    import streamlit as st

    st.markdown(FOOTER_HTML, unsafe_allow_html=True)
