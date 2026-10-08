"""Small plotly chart builders shared by the app's tabs. Single axis only,
fixed categorical color order, thin lines, and a hover tooltip on every mark
per the project's chart style guide."""

import plotly.graph_objects as go

from garminreader.dashboard import colors


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


def line_chart(df, x: str, y: str, y_title: str = "", hover_suffix: str = "") -> go.Figure:
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


def multi_line_chart(df, x: str, series: dict[str, str], y_title: str = "") -> go.Figure:
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


def stacked_area_chart(df, x: str, series: dict[str, str], y_title: str = "") -> go.Figure:
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


def bar_chart(df, x: str, y: str, y_title: str = "") -> go.Figure:
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
