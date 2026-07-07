"""DuckDB connection helper for the Streamlit dashboard.

The dashboard reads from a local DuckDB file (``streamlit_app/data/analytics.duckdb``),
which is the project's sole data source. Tables live under a ``marts`` schema so the
page SQL (``FROM marts.<table>``) resolves directly. The app has no cloud dependency.
"""

import os
from pathlib import Path

import duckdb
import streamlit as st

# Ships inside the repo so it reaches Streamlit Community Cloud. The file is
# NOT named "marts" on purpose: DuckDB derives the catalog name from the
# filename, which would then collide with the ``marts`` schema below.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.duckdb"


def _db_path() -> Path:
    return Path(os.environ.get("DUCKDB_PATH", DEFAULT_DB_PATH))


@st.cache_resource
def get_connection():
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB file not found at {path}. Place the dataset there, "
            "or point DUCKDB_PATH at it."
        )
    return duckdb.connect(str(path), read_only=True)


@st.cache_data(ttl=600)
def query(sql: str, params: tuple = ()):
    # A fresh cursor per call keeps concurrent Streamlit reruns thread-safe.
    # Free-text widget input must arrive via `params` (bound as `?`
    # placeholders), never interpolated into the SQL string.
    return get_connection().cursor().execute(sql, params or None).df()
