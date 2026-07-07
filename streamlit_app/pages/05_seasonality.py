"""Festival seasonality — monthly concert distribution."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Festival Seasonality")
st.markdown("When do metal bands play the most? Is there a festival season?")

df = query("SELECT * FROM marts.agg_festival_seasonality")

fig = px.bar(
    df,
    x="month_name",
    y="concert_count",
    color="unique_bands",
    text_auto=True,
    labels={
        "month_name": "Month",
        "concert_count": "Concerts",
        "unique_bands": "Unique Bands",
    },
    title="Metal Concerts by Month",
)
st.plotly_chart(fig, width='stretch')

fig2 = px.line(
    df,
    x="month_name",
    y="unique_countries",
    markers=True,
    labels={"month_name": "Month", "unique_countries": "Countries"},
    title="Geographic Spread by Month",
)
st.plotly_chart(fig2, width='stretch')
