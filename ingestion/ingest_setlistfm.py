"""Fetch Setlist.fm data for the top Metal Archives bands (local only).

Ranks bands by total review count from the Kaggle discography CSV (top 200 by
default; override with ``SETLISTFM_TOP_BANDS``), resolves each to a Setlist.fm
artist, pages through their **complete** setlist history, and writes three
CSVs to ``data/raw/setlistfm/``: ``setlists.csv``, ``songs.csv``,
``band_mapping.csv``.

Progress is checkpointed per band (``checkpoint.json``) so the run is
resumable — this matters: a full-history run for 200 bands is thousands of
API calls and can take hours, or span days if the API key's daily quota runs
out (the script exits cleanly when it does; just re-run to continue). The
checkpoint records the run configuration; if it changes (e.g. more bands, or
outputs produced by the old capped fetch), existing outputs are archived to a
``backup-*/`` subdir and the extraction starts fresh.

Requires the Kaggle data (run ``ingest_kaggle.py`` first) and a
``SETLISTFM_API_KEY`` in the repo-root ``.env`` or the environment.

Dependencies are declared inline (PEP 723) and pinned, so the script runs in
its own isolated environment without touching the dashboard's deps:

    uv run ingestion/ingest_setlistfm.py
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["requests==2.32.5"]
# ///

import csv
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

from _env import REPO_ROOT, load_env

load_env()

API_KEY = os.environ.get("SETLISTFM_API_KEY")
if not API_KEY:
    raise RuntimeError("Set SETLISTFM_API_KEY in .env or the environment.")

BASE_URL = "https://api.setlist.fm/rest/1.0"
HEADERS = {"Accept": "application/json", "x-api-key": API_KEY}
RATE_LIMIT_DELAY = 0.6  # ~1.7 req/sec, safely under Setlist.fm's 2/sec limit
MAX_RETRIES = 6

TOP_BANDS = int(os.environ.get("SETLISTFM_TOP_BANDS", "200"))
# Config stamped into the checkpoint; a mismatch (older capped run, different
# band count) archives the outputs and starts fresh so partial-history data
# never mixes with full-history data.
RUN_CONFIG = {"top_bands": TOP_BANDS, "full_history": True}

DATA_DIR = REPO_ROOT / "data" / "raw" / "metal_archives"
OUT_DIR = REPO_ROOT / "data" / "raw" / "setlistfm"
OUT_DIR.mkdir(parents=True, exist_ok=True)


class RateLimitExhausted(Exception):
    """Raised when the API keeps returning 429 after all retries (daily quota)."""


def get_top_bands(n: int) -> list[dict]:
    """Return the top N bands by total review count from the Kaggle CSVs."""
    review_counts: Counter[str] = Counter()
    with open(DATA_DIR / "all_bands_discography.csv") as f:
        for row in csv.DictReader(f):
            r = row.get("Reviews", "")
            if r and r != "No Reviews":
                try:
                    review_counts[row["Band ID"]] += int(r.split("(")[0].strip())
                except ValueError:
                    pass

    top_ids = {bid for bid, _ in review_counts.most_common(n)}

    bands, seen = [], set()
    with open(DATA_DIR / "metal_bands.csv") as f:
        for row in csv.DictReader(f):
            # "Band ID" is unreliable; the URL's trailing number is the real id.
            m = re.search(r"(\d+)$", row.get("URL", ""))
            if not m:
                continue
            bid = row["Band ID"] = m.group(1)
            if bid in top_ids and bid not in seen:
                bands.append(row)
                seen.add(bid)
    return bands


def api_get(url: str, params: dict | None = None) -> requests.Response | None:
    """GET with rate limiting and retry/backoff on HTTP 429.

    Honors ``Retry-After`` when present; otherwise backs off exponentially.
    Raises RateLimitExhausted once retries run out, so the caller can exit
    cleanly with progress checkpointed instead of crashing mid-band.
    """
    resp = None
    for attempt in range(MAX_RETRIES):
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(url, headers=HEADERS, params=params)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 10 * 2**attempt
            print(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(wait)
            continue
        return resp
    raise RateLimitExhausted(
        "Still rate-limited after all retries — likely the API key's daily quota."
    )


def search_artist(name: str) -> dict | None:
    """Resolve an artist by name; prefer an exact (case-insensitive) match."""
    resp = api_get(f"{BASE_URL}/search/artists", {"artistName": name, "sort": "relevance"})
    if resp is None or resp.status_code == 404:
        return None
    resp.raise_for_status()
    artists = resp.json().get("artist", [])
    for artist in artists:
        if artist.get("name", "").lower() == name.lower():
            return artist
    return artists[0] if artists else None


def fetch_setlists(mbid: str) -> list[dict]:
    """Fetch the complete setlist history for an artist MBID (all pages)."""
    all_setlists: list[dict] = []
    page = 1
    while True:
        resp = api_get(f"{BASE_URL}/artist/{mbid}/setlists", {"p": page})
        if resp is None or resp.status_code == 404:
            break
        resp.raise_for_status()
        data = resp.json()
        setlists = data.get("setlist", [])
        if not setlists:
            break
        all_setlists.extend(setlists)
        total = int(data.get("total", 0))
        items_per_page = int(data.get("itemsPerPage", 20))
        if page * items_per_page >= total:
            break
        page += 1
    return all_setlists


def flatten_setlist(setlist: dict) -> tuple[dict, list[dict]]:
    """Flatten a setlist JSON into one setlist record and its song records."""
    venue = setlist.get("venue", {})
    city = venue.get("city", {})
    country = city.get("country", {})
    coords = city.get("coords", {})

    setlist_record = {
        "setlist_id": setlist.get("id", ""),
        "artist_mbid": setlist.get("artist", {}).get("mbid", ""),
        "artist_name": setlist.get("artist", {}).get("name", ""),
        "event_date": setlist.get("eventDate", ""),
        "venue_id": venue.get("id", ""),
        "venue_name": venue.get("name", ""),
        "city_name": city.get("name", ""),
        "state": city.get("state", ""),
        "country_code": country.get("code", ""),
        "country_name": country.get("name", ""),
        "latitude": coords.get("lat"),
        "longitude": coords.get("long"),
        "tour_name": setlist.get("tour", {}).get("name", "") if setlist.get("tour") else "",
    }

    songs = []
    for s in setlist.get("sets", {}).get("set", []):
        set_name = s.get("name", "")
        encore = s.get("encore", 0)
        for song in s.get("song", []):
            cover = song.get("cover", {})
            songs.append({
                "setlist_id": setlist.get("id", ""),
                "song_name": song.get("name", ""),
                "set_name": set_name,
                "encore": encore,
                "is_cover": bool(cover),
                "cover_artist_name": cover.get("name", "") if cover else "",
                "is_tape": song.get("tape", False),
            })

    return setlist_record, songs


SETLIST_FIELDS = [
    "setlist_id", "artist_mbid", "artist_name", "event_date", "venue_id",
    "venue_name", "city_name", "state", "country_code", "country_name",
    "latitude", "longitude", "tour_name",
]
SONG_FIELDS = [
    "setlist_id", "song_name", "set_name", "encore", "is_cover",
    "cover_artist_name", "is_tape",
]
MAPPING_FIELDS = [
    "ma_band_id", "ma_band_name", "sfm_mbid", "sfm_artist_name", "match_type",
]

OUTPUT_FILES = ["setlists.csv", "songs.csv", "band_mapping.csv", "checkpoint.json"]


def init_csv(path: Path, fieldnames: list[str]) -> None:
    """Write a CSV header if the file does not yet exist."""
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()


def append_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Append rows to an existing CSV."""
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writerows(rows)


def load_checkpoint(path: Path) -> set[str]:
    """Return processed band IDs, archiving outputs if the run config changed.

    Legacy checkpoints (a bare JSON list, from the old top-50 / 5-page runs)
    never match RUN_CONFIG, so their partial outputs get archived too.
    """
    if not path.exists():
        return set()

    state = json.loads(path.read_text())
    if isinstance(state, dict) and state.get("config") == RUN_CONFIG:
        return set(state.get("processed", []))

    backup_dir = OUT_DIR / time.strftime("backup-%Y%m%d-%H%M%S")
    backup_dir.mkdir()
    for name in OUTPUT_FILES:
        f = OUT_DIR / name
        if f.exists():
            f.rename(backup_dir / name)
    print(f"Run config changed — archived previous outputs to {backup_dir}")
    return set()


def save_checkpoint(path: Path, processed: set[str]) -> None:
    path.write_text(json.dumps({"config": RUN_CONFIG, "processed": sorted(processed)}))


def main() -> None:
    print(f"Loading top {TOP_BANDS} bands by review count...")
    bands = get_top_bands(TOP_BANDS)
    print(f"Found {len(bands)} bands to query")

    checkpoint_path = OUT_DIR / "checkpoint.json"
    processed = load_checkpoint(checkpoint_path)
    if processed:
        print(f"Resuming - {len(processed)} bands already processed")

    setlists_path = OUT_DIR / "setlists.csv"
    songs_path = OUT_DIR / "songs.csv"
    mapping_path = OUT_DIR / "band_mapping.csv"
    init_csv(setlists_path, SETLIST_FIELDS)
    init_csv(songs_path, SONG_FIELDS)
    init_csv(mapping_path, MAPPING_FIELDS)

    total_setlists = total_songs = 0

    for i, band in enumerate(bands):
        band_id, band_name = band["Band ID"], band["Name"]
        if band_id in processed:
            continue

        print(f"[{i+1}/{len(bands)}] Searching: {band_name}...")
        try:
            artist = search_artist(band_name)

            if artist is None:
                print("  Not found on Setlist.fm")
                processed.add(band_id)
                save_checkpoint(checkpoint_path, processed)
                continue

            mbid = artist.get("mbid", "")
            match_type = "exact" if artist.get("name", "").lower() == band_name.lower() else "fuzzy"
            print(f"  Matched: {artist.get('name', '')} (mbid={mbid}, {match_type})")

            setlists = fetch_setlists(mbid)
            print(f"  Got {len(setlists)} setlists")
        except RateLimitExhausted as e:
            # This band's data was NOT written; it re-fetches on the next run.
            print(f"\n{e}")
            print(f"Progress saved ({len(processed)}/{len(bands)} bands). Re-run to resume.")
            sys.exit(75)  # EX_TEMPFAIL

        setlist_records, song_records = [], []
        for sl in setlists:
            rec, songs = flatten_setlist(sl)
            setlist_records.append(rec)
            song_records.extend(songs)

        # All writes for a band happen together, right before its checkpoint,
        # so a crash can never leave a mapping row without its setlists.
        append_csv(mapping_path, [{
            "ma_band_id": band_id,
            "ma_band_name": band_name,
            "sfm_mbid": mbid,
            "sfm_artist_name": artist.get("name", ""),
            "match_type": match_type,
        }], MAPPING_FIELDS)
        if setlist_records:
            append_csv(setlists_path, setlist_records, SETLIST_FIELDS)
        if song_records:
            append_csv(songs_path, song_records, SONG_FIELDS)

        total_setlists += len(setlist_records)
        total_songs += len(song_records)

        processed.add(band_id)
        save_checkpoint(checkpoint_path, processed)

    print(f"\nDone! Total this run: {total_setlists} setlists, {total_songs} songs")


if __name__ == "__main__":
    main()
