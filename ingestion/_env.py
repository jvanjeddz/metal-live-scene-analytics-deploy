"""Minimal .env loader so the extraction scripts are self-contained.

Reads ``KEY=VALUE`` lines from the repo-root ``.env`` (if present) into
``os.environ`` without pulling in python-dotenv. Existing environment
variables win, so an explicit ``export`` still overrides the file.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from ``.env`` into os.environ (non-overriding)."""
    env_path = path or (REPO_ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)
