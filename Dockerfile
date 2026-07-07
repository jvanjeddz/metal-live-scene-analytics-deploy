FROM python:3.13-slim

RUN groupadd -g 1000 app && useradd -u 1000 -g app -m app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Only the slim dashboard deps are installed. The ingestion scripts under
# ingestion/ declare their own pinned deps inline (PEP 723) and resolve them at
# `uv run` time, so they are intentionally absent from this locked environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && chown -R app:app /app

# .dockerignore keeps .env and data/raw out of the image (see that file).
COPY --chown=app:app . .

USER app
