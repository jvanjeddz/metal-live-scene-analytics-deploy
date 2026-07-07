"""Metal Live Scene Analytics — Main Dashboard."""

from pathlib import Path

import streamlit as st
import utils.charts  # noqa: F401 — registers Plotly theme

# LOGO = str(Path(__file__).resolve().parent.parent / "logo.png")

st.set_page_config(
    page_title="Metal Live Scene Analytics",
    # page_icon=LOGO,
    layout="wide",
)

st.title("Metal Live Scene Analytics")
st.markdown(
    """
    How does the metal music live performance landscape relate to recorded music reception?

    This dashboard links **Metal Archives** data (bands, albums, reviews) with
    **Setlist.fm** data (concert setlists) to reveal patterns in touring, genre trends,
    geographic distribution, and most-performed songs.

    *Coverage note: concert data is intended to track the ~200 most-reviewed bands' documented
    setlists, so it reflects those bands' touring histories — weighted toward the
    most fan-documented acts — not the entire live scene. Band, album, and review
    data is a Metal Archives snapshot through November 2024; concert data runs
    through mid-2026.*

    This project uses data from Metal Archives and Setlist.fm for educational purposes only.

    Use the sidebar to navigate between pages.
    """
)

from utils.db import query

col1, col2, col3, col4 = st.columns(4)
with col1:
    bands = query("SELECT count(*) as n FROM marts.dim_bands WHERE has_setlist_data")
    st.metric("Bands with Setlist Data", f"{bands['n'].iloc[0]:,}")
with col2:
    concerts = query("SELECT count(*) as n FROM marts.fct_concerts")
    st.metric("Total Concerts", f"{concerts['n'].iloc[0]:,}")
with col3:
    songs = query("SELECT count(*) as n FROM marts.agg_top_songs")
    st.metric("Unique Songs Performed", f"{songs['n'].iloc[0]:,}")
with col4:
    countries = query("SELECT count(*) as n FROM marts.agg_concerts_by_country")
    st.metric("Countries", f"{countries['n'].iloc[0]:,}")
