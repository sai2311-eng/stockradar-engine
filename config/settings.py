"""
config/settings.py
Generic, secret-free configuration loaded from the environment.

Copy .env.example to .env and fill in whatever your data feed / execution layer
needs. The open engine itself needs nothing here — these are conveniences for
the host app you build on top of it.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ModuleNotFoundError:
    # python-dotenv is optional; environment variables still work without it.
    pass


def get(key: str, default: str = "") -> str:
    """Read an optional environment variable."""
    return os.getenv(key, default)


def require(key: str) -> str:
    """Read a required environment variable, or raise with a clear message."""
    val = os.getenv(key, "")
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and set it."
        )
    return val


# ── Engine runtime knobs (safe defaults) ─────────────────────────────────
TICK_INTERVAL_SEC = int(get("TICK_INTERVAL_SEC", "60"))
LOG_LEVEL = get("LOG_LEVEL", "INFO")

# ── Universe ─────────────────────────────────────────────────────────────
# Comma-separated symbols the runner exposes to strategies. Override in .env.
UNIVERSE = [s.strip() for s in get("UNIVERSE", "").split(",") if s.strip()]
