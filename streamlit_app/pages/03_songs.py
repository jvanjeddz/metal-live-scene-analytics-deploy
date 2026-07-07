"""Most-played songs across metal concerts."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Most-Played Songs")

# Tile 6: Top Songs
n = st.slider("Number of songs to show", 10, 50, 30)
df_songs = query(f"""
    SELECT * FROM marts.agg_top_songs
    ORDER BY performance_count DESC
    LIMIT {n}
""")
df_songs["label"] = df_songs["song_name"] + " — " + df_songs["artist_name"]

fig6 = px.bar(
    df_songs,
    x="performance_count",
    y="label",
    orientation="h",
    color="unique_venue_count",
    labels={
        "performance_count": "Times Performed",
        "label": "",
        "unique_venue_count": "Unique Venues",
    },
    title=f"Top {n} Most-Performed Metal Songs",
)
fig6.update_layout(yaxis=dict(autorange="reversed"), height=max(400, n * 20))
st.plotly_chart(fig6, width='stretch')
