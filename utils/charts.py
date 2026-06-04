"""
Relief Docket – Plotly chart builders.

All chart functions return a Plotly Figure (or None on empty data).
Chart color conventions:
  Grant/favorable = #1e8a50 (green)
  Removal/denial  = #c0392b (red)
  Pending         = #2980b9 (blue)
  Pro se          = #e67e22 (orange)
  Represented     = #1e8a50 (green)
  Administration bands:
    Obama   = #3498db
    Trump 1 = #e74c3c
    Biden   = #2980b9
    Trump 2 = #c0392b
"""

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Administration shading helper ─────────────────────────────────────────────
ADMIN_BANDS = [
    {"label": "Obama",    "start": 2009, "end": 2017, "color": "rgba(52,152,219,0.10)"},
    {"label": "Trump I",  "start": 2017, "end": 2021, "color": "rgba(231,76,60,0.10)"},
    {"label": "Biden",    "start": 2021, "end": 2025, "color": "rgba(41,128,185,0.10)"},
    {"label": "Trump II", "start": 2025, "end": 2029, "color": "rgba(192,57,43,0.10)"},
]


def _add_admin_bands(fig: go.Figure, x_axis: str = "x") -> go.Figure:
    """Add semi-transparent administration shading to a figure."""
    for band in ADMIN_BANDS:
        fig.add_vrect(
            x0=band["start"],
            x1=band["end"],
            fillcolor=band["color"],
            line_width=0,
            annotation_text=band["label"],
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color="#666",
        )
    return fig


# ── Backlog timeline ──────────────────────────────────────────────────────────

def backlog_timeline_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """
    Line chart of pending caseload over time.
    Expects columns: fiscal_year (int), pending_cases (int).
    """
    if df is None or df.empty:
        return None
    fig = px.line(
        df,
        x="fiscal_year",
        y="pending_cases",
        labels={"fiscal_year": "Fiscal Year", "pending_cases": "Pending Cases"},
        title="Immigration Court Backlog — Pending Cases Over Time",
        color_discrete_sequence=["#2980b9"],
    )
    fig = _add_admin_bands(fig)
    fig.update_traces(line_width=2.5)
    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Fiscal Year",
        yaxis_title="Pending Cases",
        yaxis_tickformat=",",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Case outcomes over time ───────────────────────────────────────────────────

def outcome_trend_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """
    Stacked bar of case outcomes by fiscal year.
    Expects columns: fiscal_year, outcome_type, case_count.
    """
    if df is None or df.empty:
        return None
    color_map = {
        "Granted": "#1e8a50",
        "Removed": "#c0392b",
        "Voluntary Departure": "#e67e22",
        "Terminated": "#8e44ad",
        "Dismissed": "#7f8c8d",
        "Other": "#bdc3c7",
        "In Absentia": "#922b21",
        "Admin Closed": "#2980b9",
    }
    fig = px.bar(
        df,
        x="fiscal_year",
        y="case_count",
        color="outcome_type",
        barmode="stack",
        color_discrete_map=color_map,
        labels={"fiscal_year": "Fiscal Year", "case_count": "Cases", "outcome_type": "Outcome"},
        title="Case Outcomes by Fiscal Year",
    )
    fig.update_layout(
        hovermode="x unified",
        yaxis_tickformat=",",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
        legend_title_text="Outcome",
    )
    return fig


# ── Grant rate trend ──────────────────────────────────────────────────────────

def grant_rate_trend_chart(
    df: pd.DataFrame,
    group_col: str = "fiscal_year",
    rate_col: str = "asylum_grant_rate",
    title: str = "Asylum Grant Rate Over Time",
) -> Optional[go.Figure]:
    """
    Line chart of grant rate over time.
    Expects columns: {group_col} (int), {rate_col} (float 0–1).
    """
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df[rate_col] = plot_df[rate_col] * 100  # convert to percent

    fig = px.line(
        plot_df,
        x=group_col,
        y=rate_col,
        labels={group_col: group_col.replace("_", " ").title(), rate_col: "Grant Rate (%)"},
        title=title,
        color_discrete_sequence=["#1e8a50"],
    )
    if group_col == "fiscal_year":
        fig = _add_admin_bands(fig)
    fig.update_traces(line_width=2.5)
    fig.update_layout(
        hovermode="x unified",
        yaxis_ticksuffix="%",
        yaxis_range=[0, 100],
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Representation gap ────────────────────────────────────────────────────────

def representation_gap_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    """
    Side-by-side bar: grant rates for represented vs. pro se respondents.
    Expects columns: fiscal_year, represented_grant_rate, prose_grant_rate (floats 0–1).
    """
    if df is None or df.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["fiscal_year"],
        y=df["represented_grant_rate"] * 100,
        name="With Attorney",
        line=dict(color="#1e8a50", width=2.5),
        mode="lines+markers",
    ))
    fig.add_trace(go.Scatter(
        x=df["fiscal_year"],
        y=df["prose_grant_rate"] * 100,
        name="Pro Se (No Attorney)",
        line=dict(color="#e67e22", width=2.5, dash="dash"),
        mode="lines+markers",
    ))
    fig.update_layout(
        title="Asylum Grant Rate: Represented vs. Pro Se Respondents",
        xaxis_title="Fiscal Year",
        yaxis_title="Grant Rate (%)",
        yaxis_ticksuffix="%",
        yaxis_range=[0, 100],
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Judge bar chart ───────────────────────────────────────────────────────────

def judge_grant_rate_chart(df: pd.DataFrame, top_n: int = 30) -> Optional[go.Figure]:
    """
    Horizontal bar chart of judge asylum grant rates.
    Expects columns: judge_name, asylum_grant_rate, total_cases.
    """
    if df is None or df.empty:
        return None
    plot_df = (
        df.dropna(subset=["asylum_grant_rate", "total_cases"])
        .query("total_cases >= 50")
        .nlargest(top_n, "total_cases")
        .sort_values("asylum_grant_rate")
        .copy()
    )
    if plot_df.empty:
        return None

    plot_df["grant_pct"] = plot_df["asylum_grant_rate"] * 100
    colors = ["#1e8a50" if v >= 50 else "#c0392b" for v in plot_df["grant_pct"]]

    fig = go.Figure(go.Bar(
        x=plot_df["grant_pct"],
        y=plot_df["judge_name"],
        orientation="h",
        marker_color=colors,
        text=plot_df["grant_pct"].apply(lambda v: f"{v:.1f}%"),
        textposition="outside",
        customdata=plot_df["total_cases"],
        hovertemplate="<b>%{y}</b><br>Grant rate: %{x:.1f}%<br>Cases: %{customdata:,}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Asylum Grant Rate by Judge (top {top_n} by caseload)",
        xaxis_title="Grant Rate (%)",
        xaxis_ticksuffix="%",
        xaxis_range=[0, 105],
        height=max(400, top_n * 22),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Court comparison bar ──────────────────────────────────────────────────────

def court_comparison_chart(
    df: pd.DataFrame,
    metric_col: str = "asylum_grant_rate",
    title: str = "Asylum Grant Rate by Court",
) -> Optional[go.Figure]:
    """
    Horizontal bar chart comparing courts on a metric.
    Expects columns: court_city, {metric_col}.
    """
    if df is None or df.empty:
        return None
    plot_df = df.dropna(subset=[metric_col]).sort_values(metric_col).copy()
    if plot_df.empty:
        return None

    is_rate = plot_df[metric_col].max() <= 1.0
    values = plot_df[metric_col] * 100 if is_rate else plot_df[metric_col]
    tick_suffix = "%" if is_rate else ""

    fig = go.Figure(go.Bar(
        x=values,
        y=plot_df["court_city"],
        orientation="h",
        marker_color="#2980b9",
        hovertemplate="<b>%{y}</b><br>" + metric_col.replace("_", " ").title() + ": %{x:.1f}" + tick_suffix + "<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_ticksuffix=tick_suffix,
        height=max(400, len(plot_df) * 20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Nationality treemap ───────────────────────────────────────────────────────

def nationality_volume_chart(df: pd.DataFrame, top_n: int = 25) -> Optional[go.Figure]:
    """
    Treemap of case volume by nationality.
    Expects columns: country_name, case_count, asylum_grant_rate.
    """
    if df is None or df.empty:
        return None
    plot_df = df.dropna(subset=["case_count"]).nlargest(top_n, "case_count").copy()
    if plot_df.empty:
        return None

    plot_df["grant_pct"] = (plot_df.get("asylum_grant_rate", pd.Series(dtype=float)) * 100).fillna(0)

    fig = px.treemap(
        plot_df,
        path=["country_name"],
        values="case_count",
        color="grant_pct",
        color_continuous_scale=["#c0392b", "#f0e442", "#1e8a50"],
        range_color=[0, 80],
        title=f"Case Volume by Nationality (top {top_n}) — color = grant rate",
        hover_data={"grant_pct": ":.1f"},
        labels={"grant_pct": "Grant Rate (%)"},
    )
    fig.update_layout(
        coloraxis_colorbar_title="Grant Rate (%)",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig


# ── Policy trend (admin closure / termination) ────────────────────────────────

def policy_trend_chart(
    df: pd.DataFrame,
    metric_col: str = "admin_closure_rate",
    title: str = "Administrative Closure Rate Over Time",
) -> Optional[go.Figure]:
    """
    Line chart with administration shading for a policy-sensitive metric.
    Expects columns: fiscal_year (int), {metric_col} (float 0–1).
    """
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    if plot_df[metric_col].max() <= 1.0:
        plot_df[metric_col] = plot_df[metric_col] * 100

    fig = px.line(
        plot_df,
        x="fiscal_year",
        y=metric_col,
        title=title,
        color_discrete_sequence=["#8e44ad"],
        labels={"fiscal_year": "Fiscal Year", metric_col: "Rate (%)"},
    )
    fig = _add_admin_bands(fig)
    fig.update_traces(line_width=2.5)
    fig.update_layout(
        hovermode="x unified",
        yaxis_ticksuffix="%",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Aptos, Segoe UI, system-ui, sans-serif",
    )
    return fig
