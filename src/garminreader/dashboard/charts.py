"""Small plotly chart builders shared by the app's tabs. Single axis only,
fixed categorical color order, thin lines, and a hover tooltip on every mark
per the project's chart style guide."""

import pandas as pd
import plotly.graph_objects as go

from garminreader.dashboard import colors, formatting


def _layout(fig: go.Figure, y_title: str = "") -> go.Figure:
    chrome = colors.chrome()
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor=chrome["surface"],
        paper_bgcolor=chrome["surface"],
        font=dict(color=chrome["secondary_ink"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, color=chrome["muted"], linecolor=chrome["grid"])
    fig.update_yaxes(
        title=y_title,
        showgrid=True,
        gridcolor=chrome["grid"],
        zeroline=False,
        color=chrome["muted"],
    )
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, y_title: str = "", hover_suffix: str = "") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df[x],
            y=df[y],
            mode="lines",
            line=dict(width=2, color=colors.sequential(), shape="spline"),
            hovertemplate=f"%{{y}}{hover_suffix}<extra></extra>",
        )
    )
    return _layout(fig, y_title)


def multi_line_chart(df: pd.DataFrame, x: str, series: dict[str, str], y_title: str = "") -> go.Figure:
    """series: {column_name: display_label}, colored in fixed categorical order."""
    fig = go.Figure()
    palette = colors.categorical()
    for i, (col, label) in enumerate(series.items()):
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[col],
                mode="lines",
                name=label,
                line=dict(width=2, color=palette[i % len(palette)]),
                hovertemplate=f"{label}: %{{y}}<extra></extra>",
            )
        )
    return _layout(fig, y_title)


def stacked_area_chart(df: pd.DataFrame, x: str, series: dict[str, str], y_title: str = "") -> go.Figure:
    fig = go.Figure()
    palette = colors.categorical()
    for i, (col, label) in enumerate(series.items()):
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[col],
                mode="lines",
                stackgroup="one",
                name=label,
                line=dict(width=0.5, color=palette[i % len(palette)]),
                hovertemplate=f"{label}: %{{y}}<extra></extra>",
            )
        )
    return _layout(fig, y_title)


def bar_chart(df: pd.DataFrame, x: str, y: str, y_title: str = "") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df[x],
            y=df[y],
            marker=dict(color=colors.sequential()),
            hovertemplate="%{y}<extra></extra>",
        )
    )
    return _layout(fig, y_title)


def stacked_bar_chart(df: pd.DataFrame, x: str, series: dict[str, str], y_title: str = "") -> go.Figure:
    """series: {column_name: display_label}, stacked bottom to top in the given order."""
    fig = go.Figure()
    palette = colors.categorical()
    for i, (col, label) in enumerate(series.items()):
        fig.add_trace(
            go.Bar(
                x=df[x],
                y=df[col],
                name=label,
                marker=dict(color=palette[i % len(palette)]),
                hovertemplate=f"{label}: %{{y:.0f}}<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack")
    return _layout(fig, y_title)


def time_trend_chart(df: pd.DataFrame, x: str, series: dict[str, str], markers: bool = False) -> go.Figure:
    """Durations in seconds over time, one line per series ({column_name: display_label}).

    The y axis reads as h:mm:ss and is reversed, so faster (better) is higher up.
    """
    fig = go.Figure()
    palette = colors.categorical()
    for i, (col, label) in enumerate(series.items()):
        data = df.dropna(subset=[col])
        fig.add_trace(
            go.Scatter(
                x=data[x],
                y=data[col],
                mode="lines+markers" if markers else "lines",
                name=label,
                line=dict(width=2, color=palette[i % len(palette)]),
                marker=dict(size=8),
                customdata=[formatting.duration(v) for v in data[col]],
                hovertemplate=f"{label}: %{{customdata}}<extra></extra>",
            )
        )
    fig = _layout(fig, "")
    values = pd.concat([df[col] for col in series]).dropna()
    if not values.empty:
        ticks = _duration_ticks(float(values.min()), float(values.max()))
        fig.update_yaxes(autorange="reversed", tickvals=ticks, ticktext=[formatting.duration(t) for t in ticks])
    return fig


def _duration_ticks(low: float, high: float, count: int = 5) -> list[float]:
    """Evenly spaced ticks on whole minutes, covering [low, high]."""
    step = max(60.0, round((high - low) / count / 60) * 60)
    start = (low // step) * step
    ticks = [start]
    while ticks[-1] < high:
        ticks.append(ticks[-1] + step)
    return ticks
