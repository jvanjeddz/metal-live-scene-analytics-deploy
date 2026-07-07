.PHONY: setup dashboard ingest ingest-kaggle ingest-setlistfm transform docker-up docker-down docker-ingest

setup:
	uv sync

dashboard:
	uv run streamlit run streamlit_app/app.py

# ─── Data ingestion ──────────────────────────────────────────────────────────────
# Build-time only. Each script declares its own pinned deps inline (PEP 723), so
# `uv run` resolves them into an isolated env — they never touch the dashboard
# dependencies. Credentials are read from `.env`. Run order matters: Setlist.fm
# ranks bands from the Kaggle discography CSV, and the transform reads both
# extractions to build the DuckDB file the dashboard ships with.

ingest: ingest-kaggle ingest-setlistfm transform

ingest-kaggle:
	uv run ingestion/ingest_kaggle.py

ingest-setlistfm:
	uv run ingestion/ingest_setlistfm.py

transform:
	uv run ingestion/build_marts.py

# ─── Docker ──────────────────────────────────────────────────────────────────────

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-ingest:
	docker compose run --rm ingest
