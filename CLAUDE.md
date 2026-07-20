# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal daily news bot. One always-on Python process researches the day's news
with the Anthropic API's web-search tool, delivers a categorized brief to Telegram
with 👍/👎 rating buttons, and feeds those ratings back into future briefs so the
curation learns the reader's taste.

## Commands

```bash
pip install -r requirements.txt      # install deps
cp .env.example .env                 # then fill in the two required secrets
python bot.py                        # run the bot (foreground; Ctrl+C to stop)
python -c "import config, curator, preferences, bot"   # import-check all modules
```

There is no test suite yet. To exercise curation without Telegram:

```bash
python -c "import curator, json; print(json.dumps(curator.generate_brief(), indent=2))"
```

To trigger a brief interactively once the bot is running, send `/brief` in Telegram.

## Architecture

The process is a single `python-telegram-bot` `Application` (`bot.py`) that owns
both scheduling and rating input:

- **`bot.py`** — Telegram wiring. `JobQueue.run_daily` fires `send_brief` at the
  configured local time; `/brief` triggers it on demand. Curation runs via
  `asyncio.to_thread` so the blocking Anthropic call never stalls the event loop.
  Each story is sent as its own message so it can carry its own inline rating
  keyboard. `on_rating` writes the vote and swaps the buttons for a confirmation.
- **`curator.py`** — the only Anthropic API caller. `generate_brief()` runs one
  streamed `messages.stream` call with the `web_search_20260209` server tool and
  adaptive thinking, looping on `stop_reason == "pause_turn"` (the server-tool
  pause). The model returns a JSON brief which is parsed, stamped with stable
  story ids (`date:cat_index:story_index`), and archived to `briefs/<date>.json`.
- **`preferences.py`** — the learning loop. Ratings append to `ratings.jsonl`;
  `build_profile()` distills recent ratings into a text block injected into the
  curator prompt.
- **`config.py`** — loads `.env` and `categories.yaml`; all tunables live here.
- **`categories.yaml`** — the categories, their emoji, `min_stories`, and the
  per-category `guidance` string that shapes what the curator looks for. Editing
  this is the main way to change the brief's coverage — no code change needed.

Data flow each morning: `preferences.build_profile()` → `curator.generate_brief()`
(web search + JSON) → `curator.save_archive()` → `bot.deliver()` → user taps
ratings → `preferences.record_rating()` → tomorrow's profile.

## Conventions that matter here

- **`curator.py` is the single source of Anthropic-API truth.** Keep the model id
  configurable via `config.MODEL` (default `claude-opus-4-8`). The web-search tool
  type, the `pause_turn` resume loop, and streaming-to-avoid-timeouts are all load
  bearing — see the comments in that file before changing them.
- **Story ids are the join key** between a delivered message, its archive entry,
  and its rating. The format `date:cat_index:story_index` is embedded in Telegram
  `callback_data`; keep it short (Telegram caps callback_data at 64 bytes).
- **Secrets live only in `.env`** (git-ignored). `ratings.jsonl` and `briefs/` are
  local runtime state and are also git-ignored.
