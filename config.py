"""Central configuration: loads secrets/settings from .env and categories from
categories.yaml. Import `config` and read attributes; nothing here does I/O
beyond loading those two files once at import time."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# --- Secrets / required ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Optional / defaults ---
MODEL = os.environ.get("MODEL", "claude-opus-4-8")
TIMEZONE = os.environ.get("TIMEZONE", "America/New_York")
BRIEF_HOUR = int(os.environ.get("BRIEF_HOUR", "7"))
BRIEF_MINUTE = int(os.environ.get("BRIEF_MINUTE", "0"))

# --- Data files (created on demand) ---
BRIEFS_DIR = BASE_DIR / "briefs"
RATINGS_FILE = BASE_DIR / "ratings.jsonl"
CATEGORIES_FILE = BASE_DIR / "categories.yaml"


def load_categories() -> list[dict]:
    """Return the category definitions from categories.yaml."""
    with open(CATEGORIES_FILE, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cats = data.get("categories", [])
    for c in cats:
        c.setdefault("min_stories", 1)
        c.setdefault("emoji", "•")
    return cats


def missing_required() -> list[str]:
    """Return the names of any required settings that are not set."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    return missing
