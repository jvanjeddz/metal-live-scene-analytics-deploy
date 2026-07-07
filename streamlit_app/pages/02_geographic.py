"""Geographic distribution of metal concerts."""

import plotly.express as px
import streamlit as st
import utils.charts  # noqa: F401

from utils.db import query

st.header("Geographic Distribution")

# Tile 5: Concert Heatmap by Country
df_country = query("SELECT * FROM marts.agg_concerts_by_country")

# Map ISO alpha-2 to alpha-3 for Plotly choropleth
ALPHA2_TO_ALPHA3 = {
    "AD": "AND", "AE": "ARE", "AF": "AFG", "AG": "ATG", "AL": "ALB",
    "AM": "ARM", "AO": "AGO", "AR": "ARG", "AT": "AUT", "AU": "AUS",
    "AZ": "AZE", "BA": "BIH", "BB": "BRB", "BD": "BGD", "BE": "BEL",
    "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN", "BN": "BRN",
    "BO": "BOL", "BR": "BRA", "BS": "BHS", "BT": "BTN", "BW": "BWA",
    "BY": "BLR", "BZ": "BLZ", "CA": "CAN", "CD": "COD", "CF": "CAF",
    "CG": "COG", "CH": "CHE", "CI": "CIV", "CL": "CHL", "CM": "CMR",
    "CN": "CHN", "CO": "COL", "CR": "CRI", "CU": "CUB", "CY": "CYP",
    "CZ": "CZE", "DE": "DEU", "DJ": "DJI", "DK": "DNK", "DO": "DOM",
    "DZ": "DZA", "EC": "ECU", "EE": "EST", "EG": "EGY", "ER": "ERI",
    "ES": "ESP", "ET": "ETH", "FI": "FIN", "FR": "FRA", "GA": "GAB",
    "GB": "GBR", "GE": "GEO", "GH": "GHA", "GR": "GRC", "GT": "GTM",
    "GY": "GUY", "HN": "HND", "HR": "HRV", "HT": "HTI", "HU": "HUN",
    "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ",
    "IR": "IRN", "IS": "ISL", "IT": "ITA", "JM": "JAM", "JO": "JOR",
    "JP": "JPN", "KE": "KEN", "KG": "KGZ", "KH": "KHM", "KR": "KOR",
    "KW": "KWT", "KZ": "KAZ", "LA": "LAO", "LB": "LBN", "LK": "LKA",
    "LR": "LBR", "LT": "LTU", "LU": "LUX", "LV": "LVA", "LY": "LBY",
    "MA": "MAR", "MD": "MDA", "ME": "MNE", "MG": "MDG", "MK": "MKD",
    "ML": "MLI", "MM": "MMR", "MN": "MNG", "MT": "MLT", "MX": "MEX",
    "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NE": "NER", "NG": "NGA",
    "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL",
    "OM": "OMN", "PA": "PAN", "PE": "PER", "PH": "PHL", "PK": "PAK",
    "PL": "POL", "PR": "PRI", "PT": "PRT", "PY": "PRY", "QA": "QAT",
    "RO": "ROU", "RS": "SRB", "RU": "RUS", "RW": "RWA", "SA": "SAU",
    "SE": "SWE", "SG": "SGP", "SI": "SVN", "SK": "SVK", "SN": "SEN",
    "SV": "SLV", "SY": "SYR", "TH": "THA", "TN": "TUN", "TR": "TUR",
    "TW": "TWN", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA",
    "UY": "URY", "UZ": "UZB", "VE": "VEN", "VN": "VNM", "ZA": "ZAF",
    "ZM": "ZMB", "ZW": "ZWE",
}
df_country["iso_alpha3"] = df_country["country_code"].map(ALPHA2_TO_ALPHA3)

fig5 = px.choropleth(
    df_country.dropna(subset=["iso_alpha3"]),
    locations="iso_alpha3",
    locationmode="ISO-3",
    color="concert_count",
    hover_name="country_name",
    color_continuous_scale="Reds",
    labels={"concert_count": "Concerts", "iso_alpha3": "Country"},
    title="Metal Concerts by Country",
)
fig5.update_layout(
    geo=dict(
        showframe=False,
        showcoastlines=True,
        bgcolor="rgba(0,0,0,0)",
        landcolor="rgba(0,0,0,0)",
        oceancolor="rgba(0,0,0,0)",
    ),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig5, width='stretch')

st.subheader("Top Countries")
st.dataframe(
    df_country.head(20)[["country_name", "concert_count"]],
    width='stretch',
    hide_index=True,
)
