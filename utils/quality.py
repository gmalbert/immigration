"""
Relief Docket – data quality utilities.

Documents known EOIR data quality issues and provides helpers
for displaying quality warnings in the UI.
"""

from typing import Optional
import pandas as pd

# ── Known quality issues ──────────────────────────────────────────────────────

KNOWN_ISSUES = [
    {
        "id": "disappearing_records",
        "severity": "critical",
        "title": "Disappearing Records (2019–2022)",
        "summary": (
            "Between 2019 and 2022, TRAC at Syracuse documented EOIR systematically releasing "
            "monthly extracts where records present in previous months were simply absent. "
            "At peak, over 60,000 records disappeared per month."
        ),
        "mitigation": (
            "This pipeline archives every monthly release and never deletes records from the "
            "canonical dataset — records absent from a new release are flagged, not removed."
        ),
        "sources": ["TRAC Immigration", "Congressional Hispanic Caucus", "GAO"],
    },
    {
        "id": "pre_1997_terminology",
        "severity": "high",
        "title": "Pre-1997 Terminology Shift (IIRIRA)",
        "summary": (
            "The 1996 Illegal Immigration Reform and Immigrant Responsibility Act (IIRIRA) "
            "merged deportation and exclusion proceedings into unified 'removal proceedings' "
            "effective April 1997. Pre-1997 records use different case type codes and charge structures."
        ),
        "mitigation": (
            "This site treats 1997 as a hard boundary for most longitudinal analysis. "
            "Pre-1997 data is displayed with a warning banner."
        ),
        "sources": ["EOIR", "TRAC Immigration"],
    },
    {
        "id": "admin_closure_policy",
        "severity": "medium",
        "title": "Administrative Closure — Policy-Driven Coding Shifts",
        "summary": (
            "Administrative closure was coded consistently for years, then usage spiked dramatically "
            "under Obama (2011–2016), was nearly eliminated under Trump (2017–2020), and reopened "
            "under Biden. The code itself didn't change — only the policy behind it did."
        ),
        "mitigation": (
            "The Policy Shift page explicitly annotates administrative closure charts with "
            "the relevant policy changes."
        ),
        "sources": ["TRAC Immigration", "EOIR"],
    },
    {
        "id": "outcome_code_change_2019",
        "severity": "medium",
        "title": "Application Outcome Code Change (May 2019)",
        "summary": (
            "EOIR deactivated the 'other' outcome code for applications in May 2019, replacing "
            "it with 'not adjudicated'. Code that maps the old value will silently undercount "
            "outcomes in post-2019 data."
        ),
        "mitigation": (
            "This pipeline harmonizes outcome codes across the 2019 boundary, treating both "
            "'other' and 'not adjudicated' as equivalent for historical comparisons."
        ),
        "sources": ["TRAC Immigration"],
    },
    {
        "id": "expedited_removal_excluded",
        "severity": "medium",
        "title": "Expedited Removal Not Included",
        "summary": (
            "Cases where DHS/ICE removes someone without an immigration court hearing are not "
            "in EOIR data. This is an increasingly large share of total removals and is "
            "handled entirely outside the EOIR system."
        ),
        "mitigation": (
            "All site pages note this scope limitation. EOIR data covers only cases "
            "adjudicated by immigration judges — not expedited removal by DHS."
        ),
        "sources": ["EOIR", "DHS"],
    },
    {
        "id": "paper_cases_partial",
        "severity": "low",
        "title": "Paper Cases Partially Missing",
        "summary": (
            "EOIR estimated approximately 1 million cases exist only in paper format. "
            "These appear partially or not at all in the digital data."
        ),
        "mitigation": (
            "Pre-1990 data is excluded from analysis on this site due to sparseness."
        ),
        "sources": ["EOIR FOIA documentation"],
    },
    {
        "id": "uscis_affirmative_asylum_excluded",
        "severity": "low",
        "title": "Affirmative Asylum Cases Not Included",
        "summary": (
            "Only defensive asylum claims before immigration judges are in EOIR data. "
            "Affirmative asylum filed directly with USCIS is a separate system and is "
            "not reflected here."
        ),
        "mitigation": "Noted prominently on the Nationalities and Cases pages.",
        "sources": ["USCIS", "EOIR"],
    },
]


def get_issue_by_id(issue_id: str) -> Optional[dict]:
    for issue in KNOWN_ISSUES:
        if issue["id"] == issue_id:
            return issue
    return None


def get_issues_by_severity(severity: str) -> list:
    return [i for i in KNOWN_ISSUES if i["severity"] == severity]


# ── Diff-log analysis helpers ─────────────────────────────────────────────────

def analyze_diff_summary(diff_df: pd.DataFrame) -> dict:
    """
    Analyze a diff summary DataFrame and return a quality assessment.
    Expected columns: table, prev_count, curr_count, added, deleted, deletion_rate_pct.
    """
    ALERT_THRESHOLDS = {
        "A_TblCase":        0.1,   # >0.1% case deletions
        "E_TblApplication": 0.5,   # >0.5% application deletions
        "B_TblProceeding":  0.1,
    }
    warnings = []
    for _, row in diff_df.iterrows():
        table = row.get("table", "")
        del_rate = row.get("deletion_rate_pct", 0.0)
        threshold = ALERT_THRESHOLDS.get(table, 1.0)
        if del_rate > threshold:
            warnings.append({
                "table": table,
                "deleted": int(row.get("deleted", 0)),
                "deletion_rate_pct": del_rate,
                "threshold": threshold,
                "message": (
                    f"{table}: {int(row.get('deleted', 0)):,} records deleted "
                    f"({del_rate:.3f}% of prior release). "
                    f"Threshold: {threshold}%. Investigate before publishing."
                ),
            })
    return {
        "has_alerts": len(warnings) > 0,
        "alert_count": len(warnings),
        "warnings": warnings,
    }


def completeness_by_era(df: pd.DataFrame, year_col: str = "fiscal_year") -> pd.DataFrame:
    """
    Given a DataFrame with a year column, annotate completeness confidence by era.
    Returns the input df with a 'data_quality_note' column added.
    """
    def era_note(year):
        if year < 1990:
            return "⚠ Pre-1990: sparse, many paper records"
        if year < 1997:
            return "⚠ Pre-1997: different proceeding codes (pre-IIRIRA)"
        if year < 2000:
            return "⚠ 1997–1999: transitional; use with caution"
        if year < 2016:
            return "✅ 2000–2015: most reliable era"
        return "✅ 2016+: most complete; see quality notes"

    result = df.copy()
    result["data_quality_note"] = result[year_col].apply(era_note)
    return result
