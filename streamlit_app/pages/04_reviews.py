"""Review scores: distribution by genre, plus best artists and albums."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Review Scores by Genre")
st.markdown(
    "Which genres are most critically acclaimed? Which are polarizing? "
    "Box plots show the median, quartiles, and outliers for each genre — "
    "and below, the best-reviewed artists and albums within a genre."
)

# ── Page-wide controls: grouping + release period + genres ──────────────────
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
    GENRE_COL = "t.genre_tag"
    GENRE_JOIN = "JOIN marts.band_genre_tags t USING (ma_band_id)"
    GENRE_LABEL = "Genre keyword"
    default_genres = [
        "Death", "Black", "Thrash", "Heavy",
        "Power", "Doom", "Progressive", "Melodic",
        "Symphonic", "Speed", "Grindcore", "Brutal",
        "Atmospheric", "Folk",
    ]
else:
    GENRE_COL = "r.primary_subgenre"
    GENRE_JOIN = ""
    GENRE_LABEL = "Subgenre"
    default_genres = [
        "Death Metal", "Black Metal", "Thrash Metal", "Heavy Metal",
        "Power Metal", "Doom Metal", "Progressive Metal", "Melodic Death Metal",
    ]

year_bounds = query(
    "SELECT min(year) AS lo, max(year) AS hi FROM marts.agg_album_reviews"
)
lo, hi = int(year_bounds["lo"][0]), int(year_bounds["hi"][0])
year_from, year_to = st.slider(
    "Release period", min_value=lo, max_value=hi, value=(lo, hi)
)
st.caption(
    "Album and review data is a Metal Archives snapshot through Nov 2024 — "
    "the final year is partial, and recent releases have had less time to "
    "accumulate reviews."
)

# Genres with a meaningful number of reviewed albums overall (stable list,
# independent of the year filter so selections don't vanish while sliding)
top_genres = query(f"""
    SELECT {GENRE_COL} AS genre, count(*) AS n
    FROM marts.agg_album_reviews r
    {GENRE_JOIN}
    GROUP BY 1
    HAVING count(*) >= 50
    ORDER BY n DESC
""")

available = top_genres["genre"].tolist()
defaults = [g for g in default_genres if g in available]

selected = st.multiselect(
    f"Select {GENRE_LABEL.lower()}s to compare", available, default=defaults
)

SHAPE_ORDER = ["Demo/EP only", "One album", "2-4 albums", "5-9 albums", "10+ albums"]
shapes = st.multiselect(
    "Career shape (full-length album count of the band)",
    SHAPE_ORDER,
    default=SHAPE_ORDER,
)

if not selected:
    st.info(f"Select at least one {GENRE_LABEL.lower()}.")
    st.stop()
if not shapes:
    st.info("Select at least one career shape.")
    st.stop()

placeholders = ", ".join(f"'{g}'" for g in selected)
shape_placeholders = ", ".join(f"'{s}'" for s in shapes)

# ── Tile: score distribution ────────────────────────────────────────────────
df = query(f"""
    SELECT {GENRE_COL} AS genre, r.avg_review_pct
    FROM marts.agg_album_reviews r
    {GENRE_JOIN}
    WHERE {GENRE_COL} IN ({placeholders})
      AND r.career_shape IN ({shape_placeholders})
      AND r.year BETWEEN {year_from} AND {year_to}
""")

if df.empty:
    st.info(f"No reviewed albums in this period for the selected {GENRE_LABEL.lower()}s.")
    st.stop()

# Sort genres by median score for better readability
genre_order = (
    df.groupby("genre")["avg_review_pct"]
    .median()
    .sort_values(ascending=False)
    .index.tolist()
)

fig = px.box(
    df,
    x="genre",
    y="avg_review_pct",
    color="genre",
    category_orders={"genre": genre_order},
    labels={
        "genre": GENRE_LABEL,
        "avg_review_pct": "Review Score (%)",
    },
    title=f"Review Score Distribution by {GENRE_LABEL} ({year_from}–{year_to})",
)
fig.update_layout(showlegend=False, xaxis_tickangle=-45)
st.plotly_chart(fig, width='stretch')
if mode == "Keyword tags":
    st.caption(
        "An album counts under every selected keyword its band's genre "
        "mentions, so the same album can appear in several boxes."
    )

# Summary stats table
st.subheader("Summary Statistics")
stats = (
    df.groupby("genre")["avg_review_pct"]
    .agg(["count", "mean", "median", "std", "min", "max"])
    .round(1)
    .sort_values("median", ascending=False)
    .rename(columns={
        "count": "Albums",
        "mean": "Mean",
        "median": "Median",
        "std": "Std Dev",
        "min": "Min",
        "max": "Max",
    })
)
st.dataframe(stats, width='stretch')

# ── Tiles: best-reviewed artists and albums within one genre ────────────────
st.divider()
col_genre, col_artist_min, col_album_min = st.columns(3)
with col_genre:
    genre = st.selectbox(f"Drill into a {GENRE_LABEL.lower()}", selected)
# Higher floors keep sparsely-reviewed acts out of the rankings. No album in
# the dataset exceeds ~41 reviews, hence the lower ceiling for albums.
with col_artist_min:
    MIN_ARTIST_REVIEWS = st.selectbox(
        "Min. reviews per artist", [5, 10, 20, 50, 100], index=1
    )
with col_album_min:
    MIN_ALBUM_REVIEWS = st.selectbox(
        "Min. reviews per album", [3, 5, 10, 20], index=0
    )

st.subheader(f"Best-Reviewed Artists — {genre}")
df_artists = query(f"""
    SELECT
        r.band_name,
        r.country,
        round(sum(r.avg_review_pct * r.review_count) / sum(r.review_count), 1)
            AS weighted_score,
        count(*) AS albums,
        sum(r.review_count) AS total_reviews
    FROM marts.agg_album_reviews r
    {GENRE_JOIN}
    WHERE {GENRE_COL} = '{genre}'
      AND r.career_shape IN ({shape_placeholders})
      AND r.year BETWEEN {year_from} AND {year_to}
    GROUP BY r.band_name, r.country
    HAVING sum(r.review_count) >= {MIN_ARTIST_REVIEWS}
    ORDER BY weighted_score DESC
    LIMIT 15
""")

if df_artists.empty:
    st.info(f"No artists with ≥{MIN_ARTIST_REVIEWS} reviews in this period.")
else:
    fig_artists = px.bar(
        df_artists,
        x="weighted_score",
        y="band_name",
        orientation="h",
        color="total_reviews",
        hover_data=["country", "albums"],
        labels={
            "weighted_score": "Review Score (%)",
            "band_name": "Artist",
            "total_reviews": "Total Reviews",
            "albums": "Albums",
        },
        title=f"Top {len(df_artists)} Artists by Review Score ({year_from}–{year_to})",
    )
    fig_artists.update_layout(yaxis=dict(autorange="reversed"))
    fig_artists.update_xaxes(range=[df_artists["weighted_score"].min() - 5, 100])
    st.plotly_chart(fig_artists, width='stretch')
    st.caption(
        f"Score is the review-count-weighted average across an artist's albums; "
        f"artists need ≥{MIN_ARTIST_REVIEWS} total reviews to rank."
    )

st.subheader(f"Best-Reviewed Albums — {genre}")
rank_mode = st.radio(
    "Ranking",
    ["Confidence-weighted", "Raw average"],
    horizontal=True,
    help=(
        "Confidence-weighted pulls albums with few reviews toward the "
        "genre's mean score, so a 99% with 3 reviews doesn't outrank an "
        "86% with 26. Raw average sorts on the score alone."
    ),
)
# Bayesian prior: PRIOR_WEIGHT pseudo-reviews at the genre's mean score
# (computed over the same genre/shape/period pool, before the review floor).
PRIOR_WEIGHT = 10
order_col = '"Weighted (%)"' if rank_mode == "Confidence-weighted" else '"Score (%)"'
df_albums = query(f"""
    WITH pool AS (
        SELECT r.album_name, r.band_name, r.year, r.album_type,
               r.avg_review_pct, r.review_count
        FROM marts.agg_album_reviews r
        {GENRE_JOIN}
        WHERE {GENRE_COL} = '{genre}'
          AND r.career_shape IN ({shape_placeholders})
          AND r.year BETWEEN {year_from} AND {year_to}
    ),
    prior AS (
        SELECT avg(avg_review_pct) AS mean_score FROM pool
    )
    SELECT
        album_name AS "Album",
        band_name AS "Artist",
        year AS "Year",
        album_type AS "Type",
        avg_review_pct AS "Score (%)",
        review_count AS "Reviews",
        round(
            (review_count * avg_review_pct + {PRIOR_WEIGHT} * prior.mean_score)
            / (review_count + {PRIOR_WEIGHT}),
            1
        ) AS "Weighted (%)"
    FROM pool, prior
    WHERE review_count >= {MIN_ALBUM_REVIEWS}
    ORDER BY {order_col} DESC, "Reviews" DESC
    LIMIT 15
""")

if df_albums.empty:
    st.info(f"No albums with ≥{MIN_ALBUM_REVIEWS} reviews in this period.")
else:
    st.dataframe(df_albums, width='stretch', hide_index=True)
    st.caption(
        f"Albums need ≥{MIN_ALBUM_REVIEWS} reviews to rank. The weighted score "
        f"blends each album's average with the genre's mean as if it had "
        f"{PRIOR_WEIGHT} extra reviews at that mean."
    )
