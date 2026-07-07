"""Country-genre affinity using location quotient."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Country-Genre Affinity")
st.markdown(
    """
    Which countries specialize in which genres? The **location quotient (LQ)** measures
    over-representation: LQ > 1 means a genre is more common in that country than globally.
    LQ of 5 means 5x the global average concentration.
    """
)

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
    TABLE = "marts.agg_country_tag_affinity"
    COL = "genre_tag"
    LABEL = "Genre keyword"
    DEFAULT_GENRE = "Heavy"
else:
    TABLE = "marts.agg_country_genre_affinity"
    COL = "primary_subgenre"
    LABEL = "Subgenre"
    DEFAULT_GENRE = "Heavy Metal"

# LQ is a ratio, so a handful of bands can top the chart with a huge
# quotient; the floor keeps only established scenes in the rankings.
MIN_BANDS = st.selectbox(
    "Min. bands per country-genre pair",
    [3, 10, 25, 50],
    index=1,
    help=(
        "A location quotient computed from 3-4 bands is mostly noise. "
        "Raise the floor to rank only well-populated scenes."
    ),
)

countries = query(f"SELECT DISTINCT country FROM {TABLE} ORDER BY country")
selected = st.selectbox("Select a country", countries["country"].tolist())

df = query(f"""
    SELECT * FROM {TABLE}
    WHERE country = '{selected}'
      AND band_count >= {MIN_BANDS}
    ORDER BY location_quotient DESC
    LIMIT 15
""")

if df.empty:
    st.info(f"No {LABEL.lower()} in {selected} has ≥{MIN_BANDS} bands — lower the floor.")
else:
    fig = px.bar(
        df,
        x="location_quotient",
        y=COL,
        orientation="h",
        color="band_count",
        text="band_count",
        labels={
            "location_quotient": "Location Quotient",
            COL: LABEL,
            "band_count": "Bands",
        },
        title=f"Top {LABEL} Specializations in {selected}",
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width='stretch')

# Cross-country comparison for a genre
st.subheader(f"Compare Countries for a {LABEL}")
genres = query(f"SELECT DISTINCT {COL} FROM {TABLE} ORDER BY {COL}")
genre_list = genres[COL].tolist()
default_idx = genre_list.index(DEFAULT_GENRE) if DEFAULT_GENRE in genre_list else 0
selected_genre = st.selectbox(f"Select a {LABEL.lower()}", genre_list, index=default_idx)

df2 = query(f"""
    SELECT * FROM {TABLE}
    WHERE {COL} = '{selected_genre}'
      AND band_count >= {MIN_BANDS}
    ORDER BY location_quotient DESC
""")
n_show = max(5, min(15, len(df2)))
df2 = df2.head(n_show)

if df2.empty:
    st.info(f"No country has ≥{MIN_BANDS} {selected_genre} bands — lower the floor.")
else:
    fig2 = px.bar(
        df2,
        x="location_quotient",
        y="country",
        orientation="h",
        color="band_count",
        text="band_count",
        labels={
            "location_quotient": "Location Quotient",
            "country": "Country",
            "band_count": "Bands",
        },
        title=f"Top Countries for {selected_genre}",
    )
    fig2.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig2, width='stretch')

# Genre popularity by country
st.subheader("Genre Popularity by Country")
genre_map_list = genre_list
default_map_idx = genre_map_list.index(DEFAULT_GENRE) if DEFAULT_GENRE in genre_map_list else 0
selected_genre_map = st.selectbox(
    f"Select a {LABEL.lower()}", genre_map_list, index=default_map_idx, key="genre_map"
)

n_countries = st.slider("Number of countries to show", 10, 40, 20, key="n_countries")

df_map = query(f"""
    SELECT country, band_count
    FROM {TABLE}
    WHERE {COL} = '{selected_genre_map}'
    ORDER BY band_count DESC
    LIMIT {n_countries}
""")

fig3 = px.bar(
    df_map,
    x="band_count",
    y="country",
    orientation="h",
    text="band_count",
    labels={"band_count": "Bands", "country": "Country"},
    title=f"{selected_genre_map} Bands by Country",
)
fig3.update_layout(yaxis=dict(autorange="reversed"), height=max(400, n_countries * 25))
st.plotly_chart(fig3, width='stretch')
