# Metal Live Scene Analytics

Streamlit dashboard exploring how the metal live scene relates to recorded music reception. It links **Metal Archives** data (bands, albums, reviews) with **Setlist.fm** concert setlists to show touring patterns, genre trends, geography, and most-performed songs.

The app reads a local DuckDB file committed to the repo (`streamlit_app/data/analytics.duckdb`) — no cloud services or credentials needed to run it.

## Run locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
make setup       # install dependencies
make dashboard   # open the dashboard at http://localhost:8501
```

Or with Docker: `make docker-up`.

## Rebuild the dataset (optional)

Only needed to refresh the data the dashboard ships with. Copy `.env.example` to `.env` and fill in your Kaggle and Setlist.fm API credentials, then:

```bash
make ingest      # Kaggle download → Setlist.fm extraction → DuckDB build
```

The Setlist.fm extraction is rate-limited and checkpointed — a full run takes hours and resumes automatically if re-run. To rebuild only the DuckDB file from existing raw CSVs: `make transform`.

## Deployment

Deployed on [Streamlit Community Cloud](https://streamlit.io/cloud): point the app at `streamlit_app/app.py`. Dependencies install from `requirements.txt`, and the dataset ships with the repo, so no secrets or extra configuration are required.

## Data coverage

Band, album, and review data is a Metal Archives snapshot (through November 2024). Concert data covers the ~200 most-reviewed bands' documented setlists. Data from Metal Archives and Setlist.fm is used for educational purposes only.
