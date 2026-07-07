"""Career shapes — how far bands get, by genre and era."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Career Shapes")
st.markdown(
    "How far do metal careers go? Half the archive never gets past demos and EPs; "
    "a sliver reaches ten albums. Shapes are bucketed by **full-length album count** "
    "(demos, EPs, splits, etc. don't advance a band's shape)."
)

SHAPE_ORDER = ["Demo/EP only", "One album", "2-4 albums", "5-9 albums", "10+ albums"]

df = query("SELECT * FROM marts.agg_career_shape")

# Tile 1: overall distribution
st.subheader("The Career Funnel")
overall = (
    df.groupby("career_shape", as_index=False)["band_count"]
    .sum()
    .assign(pct=lambda d: (100 * d.band_count / d.band_count.sum()).round(1))
)
fig1 = px.bar(
    overall,
    x="career_shape",
    y="band_count",
    text="pct",
    category_orders={"career_shape": SHAPE_ORDER},
    labels={"career_shape": "Career Shape", "band_count": "Bands", "pct": "%"},
    title="Bands by Career Shape (all bands with at least one release)",
)
fig1.update_traces(texttemplate="%{text}%")
st.plotly_chart(fig1, width='stretch')

# Tile 2: shape mix by genre
st.subheader("Which Genres Sustain Careers?")
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
    genre_df = query("SELECT * FROM marts.agg_career_shape_by_tag")
    GENRE_COL = "genre_tag"
    GENRE_LABEL = "Keyword"
else:
    genre_df = df
    GENRE_COL = "primary_subgenre"
    GENRE_LABEL = "Subgenre"

top_n = st.slider(f"{GENRE_LABEL}s to compare", 5, 25, 12)
genre_totals = genre_df.groupby(GENRE_COL)["band_count"].sum()
top_genres = genre_totals.nlargest(top_n).index.tolist()
mix = (
    genre_df[genre_df[GENRE_COL].isin(top_genres)]
    .groupby([GENRE_COL, "career_shape"], as_index=False)["band_count"]
    .sum()
)
mix["share_pct"] = mix.groupby(GENRE_COL)["band_count"].transform(
    lambda s: 100 * s / s.sum()
)
# Order genres by how many of their bands get past the demo stage
past_demo = (
    mix[mix.career_shape != "Demo/EP only"]
    .groupby(GENRE_COL)["share_pct"]
    .sum()
    .sort_values(ascending=False)
    .index.tolist()
)
fig2 = px.bar(
    mix,
    x="share_pct",
    y=GENRE_COL,
    color="career_shape",
    orientation="h",
    category_orders={"career_shape": SHAPE_ORDER, GENRE_COL: past_demo},
    labels={
        "share_pct": "Share of Bands (%)",
        GENRE_COL: GENRE_LABEL,
        "career_shape": "Career Shape",
    },
    title=f"Career Shape Mix — Top {top_n} {GENRE_LABEL}s by Band Count",
)
fig2.update_layout(height=max(420, 32 * top_n))
st.plotly_chart(fig2, width='stretch')
if mode == "Keyword tags":
    st.caption(
        "A band counts under every keyword its genre mentions, so the same "
        "band can contribute to several keyword rows."
    )

# Tile 3: evolution by debut decade
st.subheader("Career Shapes by Debut Decade")
decade = (
    df[df.debut_decade.between(1970, 2020)]
    .groupby(["debut_decade", "career_shape"], as_index=False)["band_count"]
    .sum()
)
decade["share_pct"] = decade.groupby("debut_decade")["band_count"].transform(
    lambda s: 100 * s / s.sum()
)
fig3 = px.bar(
    decade,
    x="debut_decade",
    y="share_pct",
    color="career_shape",
    category_orders={"career_shape": SHAPE_ORDER},
    labels={
        "debut_decade": "Debut Decade",
        "share_pct": "Share of Bands (%)",
        "career_shape": "Career Shape",
    },
    title="Career Shape Share by Debut Decade",
)
st.plotly_chart(fig3, width='stretch')
st.caption(
    "Recent decades are censored, not different: bands that debuted in the 2010s/2020s "
    "haven't had time to accumulate albums yet, so deep career shapes are undercounted. "
    "The 2020s cohort is also cut off at the Nov 2024 Metal Archives snapshot."
)

# Tile 4: reception by career shape
st.subheader("Do Longer Careers Mean Better Reviews?")
reception = df.dropna(subset=["avg_review_score"]).copy()
reception["score_x_reviews"] = reception.avg_review_score * reception.total_reviews
by_shape = reception.groupby("career_shape", as_index=False).agg(
    total_reviews=("total_reviews", "sum"), score_x_reviews=("score_x_reviews", "sum")
)
by_shape["avg_score"] = (by_shape.score_x_reviews / by_shape.total_reviews).round(1)
fig4 = px.bar(
    by_shape,
    x="career_shape",
    y="avg_score",
    text="avg_score",
    category_orders={"career_shape": SHAPE_ORDER},
    labels={"career_shape": "Career Shape", "avg_score": "Avg Review Score (%)"},
    title="Review-Weighted Average Score by Career Shape",
)
fig4.update_yaxes(range=[60, 85])
st.plotly_chart(fig4, width='stretch')

with st.expander("Data"):
    st.dataframe(df, width='stretch', hide_index=True)
