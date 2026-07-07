"""Venue map: where metal is actually played, venue by venue."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Venue Map")
st.markdown(
    "The country heatmap stops at borders — this page drops down to the "
    "venue level. Every dot is a venue, sized and colored by how many "
    "concerts it hosted, filterable by genre and period. Below: the "
    "hardest-working venues and the most genre-diverse ones."
)

# ── Page-wide controls: grouping + genre + period ───────────────────────────
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
    GENRE_LABEL = "Genre keyword"
    genre_options = query("""
        SELECT t.genre_tag AS genre, count(*) AS n
        FROM marts.fct_concerts c
        JOIN marts.band_genre_tags t USING (ma_band_id)
        GROUP BY 1
        HAVING count(*) >= 100
        ORDER BY n DESC
    """)
    # A concert counts under a keyword if its band's genre mentions it
    GENRE_FILTER = """
        AND EXISTS (
            SELECT 1 FROM marts.band_genre_tags t
            WHERE t.ma_band_id = c.ma_band_id AND t.genre_tag = ?
        )
    """
else:
    GENRE_LABEL = "Subgenre"
    genre_options = query("""
        SELECT primary_subgenre AS genre, count(*) AS n
        FROM marts.fct_concerts
        GROUP BY 1
        HAVING count(*) >= 100
        ORDER BY n DESC
    """)
    GENRE_FILTER = "AND c.primary_subgenre = ?"

ALL_GENRES = "All genres"
col_genre, col_floor = st.columns([3, 1])
with col_genre:
    genre = st.selectbox(
        GENRE_LABEL, [ALL_GENRES] + genre_options["genre"].tolist()
    )
with col_floor:
    MIN_MAP_CONCERTS = st.selectbox(
        "Min. concerts at venue", [1, 2, 5, 10, 25], index=0,
        help="Hide one-off venues to declutter the map.",
    )

year_bounds = query(
    "SELECT min(event_year) AS lo, max(event_year) AS hi FROM marts.fct_concerts"
)
lo, hi = int(year_bounds["lo"][0]), int(year_bounds["hi"][0])
year_from, year_to = st.slider(
    "Period", min_value=lo, max_value=hi, value=(lo, hi)
)

# Genre strings come from the DB but may contain quotes, so bind them
if genre == ALL_GENRES:
    genre_filter, genre_params = "", ()
else:
    genre_filter, genre_params = GENRE_FILTER, (genre,)

# ── Venue-level aggregate driving the map, KPIs, and leaderboard ────────────
# A handful of concerts lack coordinates; they drop out of this page only.
df = query(f"""
    SELECT
        c.venue_name,
        c.city_name,
        c.country_name,
        avg(c.latitude) AS latitude,
        avg(c.longitude) AS longitude,
        count(*) AS concerts,
        count(DISTINCT c.ma_band_id) AS bands
    FROM marts.fct_concerts c
    WHERE c.latitude IS NOT NULL
      AND c.event_year BETWEEN {year_from} AND {year_to}
      {genre_filter}
    GROUP BY 1, 2, 3
    HAVING count(*) >= {MIN_MAP_CONCERTS}
    ORDER BY concerts DESC
""", genre_params)

if df.empty:
    st.info("No venues match the current filters.")
    st.stop()

title_suffix = f" — {genre}" if genre != ALL_GENRES else ""

col1, col2, col3, col4 = st.columns(4)
col1.metric("Venues", f"{len(df):,}")
col2.metric("Concerts", f"{int(df['concerts'].sum()):,}")
col3.metric("Cities", f"{df.groupby(['city_name', 'country_name']).ngroups:,}")
col4.metric("Countries", f"{df['country_name'].nunique():,}")

# ── Tile: world map of venues ───────────────────────────────────────────────
# Dim-to-bright red ramp so high counts glow against the dark land
VENUE_SCALE = [(0.0, "#6b1717"), (0.5, "#c43a2e"), (1.0, "#ffa07a")]

fig_map = px.scatter_geo(
    df,
    lat="latitude",
    lon="longitude",
    size="concerts",
    color="concerts",
    color_continuous_scale=VENUE_SCALE,
    size_max=26,
    opacity=0.85,
    hover_name="venue_name",
    hover_data={
        "latitude": False,
        "longitude": False,
        "city_name": True,
        "country_name": True,
        "concerts": True,
        "bands": True,
    },
    labels={
        "city_name": "City",
        "country_name": "Country",
        "concerts": "Concerts",
        "bands": "Bands",
    },
    title=f"Metal Venues Worldwide ({year_from}–{year_to}{title_suffix})",
)
# Surface-color ring separates overlapping dots (a pale outline turns dense
# regions into white blobs); sizemin keeps one-concert venues visible.
fig_map.update_traces(
    marker=dict(line=dict(width=0.5, color="#0a0a0a"), sizemin=2)
)
fig_map.update_geos(
    projection_type="natural earth",
    showframe=False,
    showcoastlines=False,
    showland=True,
    landcolor="#1a1a1a",
    showcountries=True,
    countrycolor="#2a2a2a",
    showocean=True,
    oceancolor="rgba(0,0,0,0)",
    showlakes=False,
    bgcolor="rgba(0,0,0,0)",
)
fig_map.update_layout(height=550)
st.plotly_chart(fig_map, width='stretch')
st.caption(
    "Dot size and color both encode concert count. Drag to pan, scroll to "
    "zoom, hover for the venue's city and distinct-band count."
)

# ── Tile: hardest-working venues ────────────────────────────────────────────
st.subheader(f"Top Venues{title_suffix}")
ALL_COUNTRIES = "All countries"
countries = (
    df.groupby("country_name")["concerts"].sum().sort_values(ascending=False)
)
country = st.selectbox("Country", [ALL_COUNTRIES] + countries.index.tolist())
df_top = df if country == ALL_COUNTRIES else df[df["country_name"] == country]
df_top = df_top.head(10).copy()
df_top["venue_label"] = df_top["venue_name"] + " — " + df_top["city_name"]
fig_top = px.bar(
    df_top,
    x="concerts",
    y="venue_label",
    orientation="h",
    color="bands",
    color_continuous_scale=VENUE_SCALE,
    hover_data=["country_name"],
    labels={
        "concerts": "Concerts",
        "venue_label": "",
        "bands": "Bands",
        "country_name": "Country",
    },
    title=(
        f"Top {len(df_top)} Venues"
        + (f" in {country}" if country != ALL_COUNTRIES else "")
        + f" by Concert Count ({year_from}–{year_to})"
    ),
)
fig_top.update_layout(yaxis=dict(autorange="reversed", automargin=True))
st.plotly_chart(fig_top, width='stretch')
st.caption("Bar color shows how many distinct bands played the venue.")

# ── Tile: most genre-diverse venues ─────────────────────────────────────────
st.subheader("Most Genre-Diverse Venues")
st.markdown(
    "Which stages host the widest spread of the genre spectrum? Ranked by "
    "distinct genres booked in the period, across **all** genres (the "
    f"{GENRE_LABEL.lower()} filter above doesn't apply here)."
)
MIN_DIVERSITY_CONCERTS = st.selectbox(
    "Min. concerts to rank", [10, 25, 50, 100], index=1,
    help="Higher floors keep rarely-used venues out of the ranking.",
)
if mode == "Keyword tags":
    DIVERSITY_COL = "count(DISTINCT t.genre_tag)"
    DIVERSITY_JOIN = "JOIN marts.band_genre_tags t USING (ma_band_id)"
else:
    DIVERSITY_COL = "count(DISTINCT c.primary_subgenre)"
    DIVERSITY_JOIN = ""

df_diverse = query(f"""
    SELECT
        c.venue_name AS "Venue",
        c.city_name AS "City",
        c.country_name AS "Country",
        {DIVERSITY_COL} AS "Distinct {GENRE_LABEL}s",
        count(DISTINCT c.concert_id) AS "Concerts",
        count(DISTINCT c.ma_band_id) AS "Bands"
    FROM marts.fct_concerts c
    {DIVERSITY_JOIN}
    WHERE c.event_year BETWEEN {year_from} AND {year_to}
    GROUP BY 1, 2, 3
    HAVING count(DISTINCT c.concert_id) >= {MIN_DIVERSITY_CONCERTS}
    ORDER BY 4 DESC, 5 DESC
    LIMIT 15
""")

if df_diverse.empty:
    st.info(f"No venues with ≥{MIN_DIVERSITY_CONCERTS} concerts in this period.")
else:
    st.dataframe(df_diverse, width='stretch', hide_index=True)
    if mode == "Keyword tags":
        st.caption(
            "A venue's count includes every keyword its bands' genres "
            "mention, so compound genres contribute several tags each."
        )
