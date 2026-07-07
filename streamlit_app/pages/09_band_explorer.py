"""Band explorer — look up individual bands by name, keywords, and career."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Band Explorer")
st.markdown(
    "Find individual bands instead of aggregates. Keyword filters match the "
    "full genre string, and **all-keywords mode** finds combinations no exact "
    "subgenre can express — e.g. *Atmospheric* + *Black*."
)

SHAPE_ORDER = [
    "No releases", "Demo/EP only", "One album",
    "2-4 albums", "5-9 albums", "10+ albums",
]
SORT_OPTIONS = {
    "Total reviews": "total_reviews DESC",
    "Avg review score": "avg_review_score DESC NULLS LAST",
    "Total concerts": "total_concerts DESC",
    "Debut year (newest first)": "debut_year DESC NULLS LAST",
    "Band name": "band_name ASC",
}
RESULT_LIMIT = 200

# ── Filters ──────────────────────────────────────────────────────────────────
tag_options = query("""
    SELECT genre_tag, count(*) AS n
    FROM marts.band_genre_tags
    GROUP BY genre_tag
    HAVING count(*) >= 20
    ORDER BY n DESC
""")["genre_tag"].tolist()
country_options = query(
    "SELECT DISTINCT country FROM marts.dim_bands WHERE country IS NOT NULL ORDER BY country"
)["country"].tolist()
status_options = query(
    "SELECT DISTINCT status FROM marts.dim_bands WHERE status IS NOT NULL ORDER BY status"
)["status"].tolist()

col_name, col_country = st.columns([2, 3])
with col_name:
    name_search = st.text_input("Band name contains", "")
with col_country:
    countries = st.multiselect("Country (empty = all)", country_options)

col_tags, col_mode = st.columns([4, 1])
with col_tags:
    tags = st.multiselect("Genre keywords (empty = all)", tag_options)
with col_mode:
    match_all = st.radio("Match", ["All keywords", "Any keyword"]) == "All keywords"

col_shape, col_status, col_minrev, col_sort = st.columns(4)
with col_shape:
    shapes = st.multiselect("Career shape (empty = all)", SHAPE_ORDER)
with col_status:
    statuses = st.multiselect("Status (empty = all)", status_options)
with col_minrev:
    min_reviews = st.selectbox("Min. total reviews", [0, 5, 10, 50, 100], index=0)
with col_sort:
    sort_by = st.selectbox("Sort by", list(SORT_OPTIONS))

# ── Query — free text goes through bind params, never into the SQL string ───
where = ["1=1"]
params: list = []

if name_search.strip():
    # Escape LIKE wildcards so % and _ match literally instead of
    # broadening the search.
    term = (
        name_search.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    where.append(r"band_name ILIKE ? ESCAPE '\'")
    params.append(f"%{term}%")

if tags:
    tag_marks = ", ".join("?" * len(tags))
    having = f"HAVING count(*) = {len(tags)}" if match_all else ""
    where.append(f"""ma_band_id IN (
        SELECT ma_band_id FROM marts.band_genre_tags
        WHERE genre_tag IN ({tag_marks})
        GROUP BY ma_band_id {having}
    )""")
    params.extend(tags)

for col, values in [("country", countries), ("career_shape", shapes), ("status", statuses)]:
    if values:
        marks = ", ".join("?" * len(values))
        where.append(f"{col} IN ({marks})")
        params.extend(values)

if min_reviews:
    where.append(f"total_reviews >= {int(min_reviews)}")

where_sql = " AND ".join(where)
params = tuple(params)

total = int(query(
    f"SELECT count(*) AS n FROM marts.dim_bands WHERE {where_sql}", params
)["n"][0])

df = query(f"""
    SELECT
        ma_band_id,
        band_name,
        country,
        full_genre,
        status,
        debut_year,
        full_length_count,
        career_shape,
        avg_review_score,
        total_reviews,
        total_concerts
    FROM marts.dim_bands
    WHERE {where_sql}
    ORDER BY {SORT_OPTIONS[sort_by]}
    LIMIT {RESULT_LIMIT}
""", params)

if df.empty:
    st.info("No bands match these filters.")
    st.stop()

shown = f"showing top {RESULT_LIMIT} by {sort_by.lower()}" if total > RESULT_LIMIT else "all shown"
st.subheader(f"{total:,} bands match ({shown})")
st.dataframe(
    df.drop(columns=["ma_band_id"]).rename(columns={
        "band_name": "Band",
        "country": "Country",
        "full_genre": "Genre",
        "status": "Status",
        "debut_year": "Debut",
        "full_length_count": "Full-lengths",
        "career_shape": "Career Shape",
        "avg_review_score": "Avg Score (%)",
        "total_reviews": "Reviews",
        "total_concerts": "Concerts",
    }),
    width='stretch',
    hide_index=True,
)

# ── Band detail ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Band Detail")
pick = st.selectbox(
    "Select a band from the results",
    df.index,
    format_func=lambda i: f"{df.band_name[i]} ({df.country[i]}) — {df.full_genre[i]}",
)
band = df.loc[pick]

albums = query("""
    SELECT year, album_name, album_type, review_count, avg_review_pct
    FROM marts.agg_album_reviews
    WHERE ma_band_id = ?
    ORDER BY year
""", (band.ma_band_id,))

if albums.empty:
    st.info("No reviewed albums for this band (unreviewed releases aren't in the marts).")
else:
    if len(albums) >= 3:
        fig = px.line(
            albums,
            x="year",
            y="avg_review_pct",
            markers=True,
            hover_data=["album_name", "album_type", "review_count"],
            labels={"year": "Year", "avg_review_pct": "Review Score (%)"},
            title=f"{band.band_name} — Album Scores Over Time",
        )
        st.plotly_chart(fig, width='stretch')
    st.dataframe(
        albums.rename(columns={
            "year": "Year",
            "album_name": "Album",
            "album_type": "Type",
            "review_count": "Reviews",
            "avg_review_pct": "Score (%)",
        }),
        width='stretch',
        hide_index=True,
    )
    st.caption(
        "Reviewed releases only — albums without Metal Archives reviews aren't "
        "listed, and the discography is a snapshot through Nov 2024."
    )

concerts = query("""
    SELECT event_date, venue_name, city_name, country_name, tour_name, song_count
    FROM marts.fct_concerts
    WHERE ma_band_id = ?
    ORDER BY event_date DESC
""", (band.ma_band_id,))

if not concerts.empty:
    st.subheader(f"Concert History ({len(concerts):,} shows)")
    st.dataframe(
        concerts.rename(columns={
            "event_date": "Date",
            "venue_name": "Venue",
            "city_name": "City",
            "country_name": "Country",
            "tour_name": "Tour",
            "song_count": "Songs",
        }),
        width='stretch',
        hide_index=True,
    )
    st.caption("Setlist.fm coverage spans a limited set of bands, so most bands have no concert history here.")
