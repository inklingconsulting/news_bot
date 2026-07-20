"""Rating storage and the learned-taste profile.

Every 👍/👎 the user taps in Telegram is appended to ratings.jsonl. Before each
brief, `build_profile()` distills recent ratings into a short block of text that
is injected into the curator prompt, so the bot gradually leans toward what the
user likes and away from what they don't."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import config

# How many recent ratings to feed back into the curator prompt.
_RECENT_LIMIT = 60


def record_rating(story: dict, vote: str) -> None:
    """Append a single rating to ratings.jsonl.

    `vote` is "up" or "down". `story` is the archived story dict (see curator)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "vote": vote,
        "category": story.get("category", ""),
        "headline": story.get("headline", ""),
        "source_url": story.get("source_url", ""),
        "story_id": story.get("id", ""),
    }
    with open(config.RATINGS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_ratings() -> list[dict]:
    if not config.RATINGS_FILE.exists():
        return []
    out = []
    with open(config.RATINGS_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def build_profile() -> str:
    """Distill recent ratings into a prompt fragment describing the reader's taste.

    Returns an empty string until there is at least one rating."""
    ratings = _load_ratings()[-_RECENT_LIMIT:]
    if not ratings:
        return ""

    liked = [r for r in ratings if r["vote"] == "up"]
    disliked = [r for r in ratings if r["vote"] == "down"]

    # Per-category signal: how often the reader liked each category.
    by_cat: dict[str, list[str]] = {}
    for r in ratings:
        by_cat.setdefault(r["category"], []).append(r["vote"])

    lines = ["READER TASTE PROFILE (learned from their past ratings):"]

    if liked:
        lines.append("\nStories they marked RELEVANT (give them more like these):")
        for r in liked[-15:]:
            lines.append(f'  - [{r["category"]}] {r["headline"]}')
    if disliked:
        lines.append("\nStories they marked NOT relevant (avoid this kind):")
        for r in disliked[-15:]:
            lines.append(f'  - [{r["category"]}] {r["headline"]}')

    cat_summary = []
    for cat, votes in by_cat.items():
        ups = votes.count("up")
        cat_summary.append(f"{cat}: {ups}/{len(votes)} liked")
    if cat_summary:
        lines.append("\nBy category (liked / total rated): " + "; ".join(cat_summary))

    lines.append(
        "\nUse this to prioritize and frame stories, but always keep every category "
        "covered with at least its minimum number of stories."
    )
    return "\n".join(lines)
