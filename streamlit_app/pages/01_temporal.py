"""Temporal trends in metal live activity."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Temporal Trends")

# Tile 2: Metal Live Activity Over Time
st.subheader("Metal Concert Activity Over Time")
df_time = query("""
    SELECT
        event_year,
        sum(concert_count) as concert_count
    FROM marts.agg_concerts_over_time
    WHERE event_year >= 1980 AND event_year <= 2025
    GROUP BY event_year
    ORDER BY event_year
""")
fig2 = px.line(
    df_time,
    x="event_year",
    y="concert_count",
    labels={"event_year": "Year", "concert_count": "Concerts"},
    title="Metal Concerts per Year",
    markers=True,
)
st.plotly_chart(fig2, width='stretch')

# Tile 4: Subgenre Popularity Shifts
st.subheader("Genre Share Over Time")
mode = st.radio(
    "Genre grouping",
    ["Keyword tags", "Exact subgenres"],
    horizontal=True,
    help=(
        "Keyword tags match every compound genre containing the word "
        "(e.g. 'Progressive' also catches Progressive Death Metal); "
        "exact subgenres use the first phrase of the genre string only."
    ),
)

if mode == "Keyword tags":
    top_tags = query("""
        SELECT genre_tag, sum(concert_count) AS total
        FROM marts.agg_tag_share_over_time
        GROUP BY genre_tag
        ORDER BY total DESC
        LIMIT 20
    """)
    tag_options = top_tags["genre_tag"].tolist()
    # Ten defaults — the full shared colorway, so no two lines repeat a color
    tag_defaults = [
        t for t in [
            "Death", "Heavy", "Melodic", "Doom", "Thrash",
            "Progressive", "Black", "Power", "Groove", "Hard-Rock",
        ]
        if t in tag_options
    ]
    selected_tags = st.multiselect(
        "Genre keywords to compare", tag_options, default=tag_defaults
    )
    if selected_tags:
        placeholders = ", ".join(f"'{t}'" for t in selected_tags)
        df_tags = query(f"""
            SELECT event_year, genre_tag, concert_share_pct
            FROM marts.agg_tag_share_over_time
            WHERE event_year >= 1990 AND event_year <= 2025
              AND genre_tag IN ({placeholders})
            ORDER BY event_year
        """)
        fig4 = px.line(
            df_tags,
            x="event_year",
            y="concert_share_pct",
            color="genre_tag",
            labels={
                "event_year": "Year",
                "concert_share_pct": "Share of Concerts (%)",
                "genre_tag": "Keyword",
            },
            title="Concert Share by Genre Keyword",
            markers=True,
        )
        st.plotly_chart(fig4, width='stretch')
        st.caption(
            "A concert counts under every keyword its band's genre mentions, "
            "so shares overlap and don't sum to 100%."
        )
    else:
        st.info("Select at least one genre keyword.")
else:
    df_sub = query("""
        WITH top_genres AS (
            SELECT primary_subgenre
            FROM marts.agg_genre_touring_intensity
            ORDER BY total_concerts DESC
            LIMIT 10
        ),
        tagged AS (
            SELECT
                event_year,
                CASE WHEN primary_subgenre IN (SELECT primary_subgenre FROM top_genres)
                     THEN primary_subgenre
                     ELSE 'Other'
                END AS primary_subgenre,
                concert_share_pct
            FROM marts.agg_subgenre_share_over_time
            WHERE event_year >= 1990 AND event_year <= 2025
        )
        SELECT
            event_year,
            primary_subgenre,
            sum(concert_share_pct) AS concert_share_pct
        FROM tagged
        GROUP BY event_year, primary_subgenre
    """)
    fig4 = px.bar(
        df_sub,
        x="event_year",
        y="concert_share_pct",
        color="primary_subgenre",
        labels={
            "event_year": "Year",
            "concert_share_pct": "Share (%)",
            "primary_subgenre": "Subgenre",
        },
        title="Subgenre Concert Share Over Time",
    )
    st.plotly_chart(fig4, width='stretch')
