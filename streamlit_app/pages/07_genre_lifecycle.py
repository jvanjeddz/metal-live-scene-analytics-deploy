"""Genre lifecycle curves — rise and fall of subgenres over time."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Genre Lifecycle Curves")
st.markdown(
    "How many new bands started releasing music in each subgenre per year? "
    "Uses each band's first album year as a proxy for when they entered the scene."
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
    TABLE = "marts.agg_tag_lifecycle"
    COL = "genre_tag"
    LABEL = "Keyword"
    # Ten defaults — the full shared colorway, so no two lines repeat a color
    default_genres = [
        "Death", "Black", "Thrash", "Heavy", "Melodic",
        "Doom", "Progressive", "Power", "Groove", "Grindcore",
    ]
else:
    TABLE = "marts.agg_genre_lifecycle"
    COL = "primary_subgenre"
    LABEL = "Subgenre"
    default_genres = ["Death Metal", "Black Metal", "Thrash Metal", "Heavy Metal", "Power Metal", "Doom Metal"]

# Get top genres by total bands
top_genres = query(f"""
    SELECT {COL}, sum(new_bands) as total
    FROM {TABLE}
    GROUP BY {COL}
    ORDER BY total DESC
    LIMIT 20
""")

available = top_genres[COL].tolist()
defaults = [g for g in default_genres if g in available]

selected = st.multiselect(
    f"Select {LABEL.lower()}s to compare",
    available,
    default=defaults,
)

if selected:
    # The Metal Archives snapshot ends mid-year (currently Nov 2024), so its
    # final debut year is incomplete and would end every curve with a fake
    # collapse — drop it and keep only complete years.
    year_hi = query(f"SELECT max(debut_year) AS hi FROM {TABLE}")
    last_complete_year = int(year_hi["hi"][0]) - 1

    placeholders = ", ".join(f"'{g}'" for g in selected)
    df = query(f"""
        SELECT * FROM {TABLE}
        WHERE {COL} IN ({placeholders})
          AND debut_year <= {last_complete_year}
        ORDER BY debut_year
    """)

    fig = px.line(
        df,
        x="debut_year",
        y="new_bands",
        color=COL,
        labels={
            "debut_year": "Year",
            "new_bands": "New Bands",
            COL: LABEL,
        },
        title=f"New Bands per Year by {LABEL}",
        markers=True,
    )
    st.plotly_chart(fig, width='stretch')
    st.caption(
        f"Band data is a Metal Archives snapshot (through Nov 2024); its "
        f"incomplete final year is omitted, so curves stop at "
        f"{last_complete_year}. New bands also surface on Metal Archives "
        f"with a lag, so the last few years still undercount."
    )
    if mode == "Keyword tags":
        st.caption(
            "A band counts under every keyword its genre mentions, so "
            "keyword lines overlap (e.g. a Progressive Death Metal band "
            "adds to both Progressive and Death)."
        )

    # Cumulative view
    df_sorted = df.sort_values([COL, "debut_year"])
    df_sorted["cumulative_bands"] = df_sorted.groupby(COL)["new_bands"].cumsum()

    fig2 = px.area(
        df_sorted,
        x="debut_year",
        y="cumulative_bands",
        color=COL,
        labels={
            "debut_year": "Year",
            "cumulative_bands": "Cumulative Bands",
            COL: LABEL,
        },
        title="Cumulative Band Count Over Time",
    )
    st.plotly_chart(fig2, width='stretch')
