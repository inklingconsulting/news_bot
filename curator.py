"""News curation via the Anthropic API with the server-side web search tool.

`generate_brief()` asks Claude to research current news, judge relevance against
the reader's taste profile, and return a structured brief as JSON. The call is
synchronous and network-heavy — the bot runs it in a worker thread.

Model / thinking / web-search notes (kept in sync with the claude-api skill):
  * Web search tool type is `web_search_20260209` (dynamic filtering), which
    Opus 4.8 / Sonnet 5 support. It needs no beta header.
  * Server tools run a server-side loop that can end a turn with
    stop_reason == "pause_turn"; we resume by re-sending the assistant turn.
  * We stream (get_final_message) because tool-augmented research can be slow
    and large, which would otherwise risk an HTTP timeout.
  * Adaptive thinking is on so Claude reasons about relevance before answering.
"""

from __future__ import annotations

import json
from datetime import date

import anthropic

import config

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

_WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}

_SYSTEM = (
    "You are a sharp, well-read personal news curator. You research the day's real "
    "news with web search and produce a concise daily brief that makes the reader "
    "more informed and more interesting. You never invent stories, quotes, or URLs — "
    "every story must come from a real page you actually found via web search, and "
    "every source_url must be a real link you retrieved. Summaries are punchy and "
    "specific: what happened and why it matters, no filler."
)


def _build_prompt(profile: str) -> str:
    today = date.today().isoformat()
    cats = config.load_categories()

    cat_specs = []
    for c in cats:
        n = c["min_stories"]
        noun = "story" if n == 1 else "stories"
        cat_specs.append(
            f'- "{c["name"]}" (at least {n} {noun}): {c["guidance"].strip()}'
        )
    cat_block = "\n".join(cat_specs)
    names = ", ".join(f'"{c["name"]}"' for c in cats)

    profile_block = f"\n\n{profile}\n" if profile else ""

    return f"""Today is {today}. Build my daily news brief.

Use web search to find the freshest, most important real stories from roughly the
last 24-48 hours (the "Worth Sharing" fact may be timeless). Cover EVERY category
below, each with at least its stated minimum number of stories:

{cat_block}
{profile_block}
For each story write:
  - headline    : a tight, informative headline (your own words are fine)
  - summary     : 2-3 sentences — what happened and the key detail
  - why_relevant: one short sentence on why it matters / why it's interesting
  - source_name : the publication or site
  - source_url  : the exact URL you found via web search

When you are done researching, respond with ONE JSON object and NOTHING else
(no prose before or after, no markdown code fence). Use exactly this shape, with
categories in the order listed above:

{{
  "date": "{today}",
  "categories": [
    {{
      "name": {names.split(",")[0].strip()},
      "stories": [
        {{
          "headline": "...",
          "summary": "...",
          "why_relevant": "...",
          "source_name": "...",
          "source_url": "https://..."
        }}
      ]
    }}
  ]
}}

Categories to include, in order: {names}."""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of the model's final text block."""
    text = text.strip()
    if text.startswith("```"):
        # strip a ```json ... ``` fence if the model added one
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response.")
    return json.loads(text[start : end + 1])


def generate_brief(profile: str = "") -> dict:
    """Research and return today's brief as a dict with assigned story ids."""
    messages = [{"role": "user", "content": _build_prompt(profile)}]

    # Server-tool loop: continue on pause_turn until the model finishes.
    while True:
        with _client.messages.stream(
            model=config.MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            tools=[_WEB_SEARCH_TOOL],
            system=_SYSTEM,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    text = "".join(b.text for b in response.content if b.type == "text")
    brief = _extract_json(text)
    return _assign_ids(brief)


def _assign_ids(brief: dict) -> dict:
    """Give every story a stable id (date:cat_index:story_index) and stamp its
    category name onto it, so rating callbacks can look it up later."""
    d = brief.get("date") or date.today().isoformat()
    brief["date"] = d
    for ci, cat in enumerate(brief.get("categories", [])):
        cat_name = cat.get("name", f"cat{ci}")
        for si, story in enumerate(cat.get("stories", [])):
            story["id"] = f"{d}:{ci}:{si}"
            story["category"] = cat_name
    return brief


def save_archive(brief: dict) -> None:
    """Persist the brief to briefs/<date>.json for rating lookups and history."""
    config.BRIEFS_DIR.mkdir(exist_ok=True)
    path = config.BRIEFS_DIR / f'{brief["date"]}.json'
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(brief, fh, ensure_ascii=False, indent=2)


def find_story(story_id: str) -> dict | None:
    """Look up an archived story by its id (used when a rating button is tapped)."""
    d = story_id.split(":", 1)[0]
    path = config.BRIEFS_DIR / f"{d}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        brief = json.load(fh)
    for cat in brief.get("categories", []):
        for story in cat.get("stories", []):
            if story.get("id") == story_id:
                return story
    return None
