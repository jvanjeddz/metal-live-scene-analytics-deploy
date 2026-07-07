"""Download the Metal Archives dataset from Kaggle (local only, no cloud).

Writes three CSVs to ``data/raw/metal_archives/``:
``metal_bands.csv``, ``all_bands_discography.csv``, ``labels_roster.csv``.

Auth: reads credentials from the repo-root ``.env`` (or the ambient
environment). Either a Kaggle API token (``KAGGLE_API_TOKEN``) or the
classic username/key pair (``KAGGLE_USERNAME`` + ``KAGGLE_KEY``) works.

Dependencies are declared inline (PEP 723) and pinned, so the script runs in
its own isolated environment without touching the dashboard's deps:

    uv run ingestion/ingest_kaggle.py
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["kaggle==2.2.3"]
# ///

import os
from pathlib import Path

from _env import REPO_ROOT, load_env

DATASET = "guimacrlh/every-metal-archives-band-october-2024"
OUT_DIR = REPO_ROOT / "data" / "raw" / "metal_archives"
EXPECTED_FILES = ["metal_bands.csv", "all_bands_discography.csv", "labels_roster.csv"]


def _ensure_credentials() -> None:
    """Make Kaggle credentials visible to the SDK before it authenticates.

    The Kaggle SDK reads ``KAGGLE_USERNAME``/``KAGGLE_KEY`` (or ``~/.kaggle/
    kaggle.json``). Newer token-style credentials arrive as a single
    ``KAGGLE_API_TOKEN``; map it onto ``KAGGLE_KEY`` if that's all we have.
    """
    load_env()
    token = os.environ.get("KAGGLE_API_TOKEN")
    if token and not os.environ.get("KAGGLE_KEY"):
        os.environ["KAGGLE_KEY"] = token
    if not os.environ.get("KAGGLE_USERNAME") and not (
        Path.home() / ".kaggle" / "kaggle.json"
    ).exists():
        # The SDK can still authenticate with a token alone on recent
        # versions; surface a clear hint if it later fails.
        pass


def download_metal_archives() -> None:
    """Download and extract the Metal Archives Kaggle dataset locally."""
    if all((OUT_DIR / f).exists() for f in EXPECTED_FILES):
        print(f"Metal Archives data already present in {OUT_DIR}, skipping download.")
        return

    _ensure_credentials()

    # Imported after credentials are set: the SDK authenticates on import/construct.
    from kaggle.api.kaggle_api_extended import KaggleApi

    print(f"Downloading {DATASET} -> {OUT_DIR} ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(DATASET, path=str(OUT_DIR), unzip=True)
    print(f"Done. Files: {[f.name for f in sorted(OUT_DIR.iterdir())]}")


if __name__ == "__main__":
    download_metal_archives()
