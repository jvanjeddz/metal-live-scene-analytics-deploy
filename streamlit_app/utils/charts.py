"""Shared Plotly theme for all dashboard charts."""

import plotly.io as pio
import plotly.graph_objects as go

METAL_COLORS = [
    "#8b0000",  # dark red
    "#c0c0c0",  # silver
    "#b22222",  # firebrick
    "#696969",  # dim gray
    "#dc143c",  # crimson
    "#a9a9a9",  # dark gray
    "#ff4500",  # orange red
    "#808080",  # gray
    "#cd5c5c",  # indian red
    "#d3d3d3",  # light gray
]

LAYOUT = go.Layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#c0c0c0"),
    xaxis=dict(gridcolor="#2a2a2a", zerolinecolor="#2a2a2a"),
    yaxis=dict(gridcolor="#2a2a2a", zerolinecolor="#2a2a2a"),
    colorway=METAL_COLORS,
)

pio.templates["metal"] = go.layout.Template(layout=LAYOUT)
pio.templates.default = "metal"
