# 📱 Daily News Bot

A personal news bot that sends you a categorized daily brief on Telegram, lets you
rate each story 👍 / 🤔 / 👎, and learns your taste over time — so you stay informed
and interesting.

Each brief covers (edit in `categories.yaml`):

- 📍 **Local — Tampa Bay** — Pinellas County & Tampa local news
- 💻 **Technology** — the day's biggest tech-sector stories
- 💼 **Big Business** — markets, deals, economy
- 🌍 **World & Science** — major world events + a science item
- 😂 **Something Funny** — genuinely amusing stories
- 🧠 **Worth Sharing** — fascinating facts worth dropping on friends

...with at least two stories in every category.

## How it works

An always-on Python program on your PC uses **Claude (Anthropic API) with web
search** to research and summarize the news, sends it to you via a **Telegram bot**,
and records your ratings to tune future briefs. Each story gets three buttons —
**👍 Relevant**, **🤔 In between**, **👎 Meh** — and recent ratings steer the next
day's edition.

## Setup (about 10 minutes)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your Telegram bot

1. In Telegram, message **@BotFather**.
2. Send `/newbot`, pick a name and username.
3. Copy the **token** it gives you (looks like `123456:ABC-...`).

### 3. Get an Anthropic API key

1. Go to <https://console.anthropic.com/> → **API Keys** → create a key.
2. Add a little credit under **Billing** (a daily brief costs roughly a few cents).

### 4. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN`. Adjust
`TIMEZONE` / `BRIEF_HOUR` if you want a delivery time other than 7:00 AM
America/New_York.

### 5. Find your chat ID

```bash
python bot.py
```

In Telegram, open a chat with your new bot, send `/start`, then `/chatid`. Copy the
number it prints into `TELEGRAM_CHAT_ID` in `.env`, then stop the bot (Ctrl+C) and
start it again. Now the daily brief is scheduled.

### 6. Try it now

Send `/brief` in Telegram to get a brief immediately — no need to wait for morning.

## Keeping it running

The bot only delivers while `python bot.py` is running.

- **Simplest:** leave a terminal open running it.
- **Auto-start on login (Windows):** use **Task Scheduler** → *Create Task* →
  trigger *At log on* → action: start `python` with argument `bot.py` and *Start in*
  set to this folder. Set it to restart on failure so it stays up.

The daily job fires even if your PC was asleep at the exact time, as long as the bot
process is running when the machine is awake near that time.

## Customizing

- **Categories & focus:** edit `categories.yaml` — add/remove categories, change
  `min_stories`, or rewrite the `guidance` to steer what each section looks for.
- **Delivery time / model:** edit `.env`.
- **Ratings:** every tap is stored in `ratings.jsonl`; the last ~60 shape each new
  brief. Delete the file to reset the bot's sense of your taste.

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Telegram bot + daily scheduler (run this) |
| `curator.py` | Anthropic API + web search → structured brief |
| `preferences.py` | stores ratings, builds the learned taste profile |
| `config.py` | loads `.env` and `categories.yaml` |
| `categories.yaml` | your categories and what each should contain |
| `briefs/` | archived briefs (auto-created) |
| `ratings.jsonl` | your rating history (auto-created) |
