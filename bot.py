"""Telegram bot entry point.

One always-on process that:
  * schedules the daily brief (JobQueue) and can send one on demand (/brief),
  * delivers each story as its own message with 👍 / 👎 rating buttons,
  * records taps so future briefs learn the reader's taste (see preferences.py).

Run it with:  python bot.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import logging
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
import curator
import preferences

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("news_bot")

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
# Vote value -> (button label, confirmation label). "mid" is the in-between option.
_VOTES = {
    "up":   ("👍 Relevant", "👍 Marked relevant"),
    "mid":  ("🤔 In between", "🤔 Noted — somewhat relevant"),
    "down": ("👎 Meh", "👎 Noted — less like this"),
}


def _story_markup(story_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_VOTES["up"][0], callback_data=f"v|up|{story_id}"),
                InlineKeyboardButton(_VOTES["mid"][0], callback_data=f"v|mid|{story_id}"),
                InlineKeyboardButton(_VOTES["down"][0], callback_data=f"v|down|{story_id}"),
            ]
        ]
    )


def _story_html(story: dict) -> str:
    headline = html.escape(story.get("headline", "").strip())
    summary = html.escape(story.get("summary", "").strip())
    why = html.escape(story.get("why_relevant", "").strip())
    src_name = html.escape(story.get("source_name", "source").strip() or "source")
    url = story.get("source_url", "").strip()

    parts = [f"<b>{headline}</b>", summary]
    if why:
        parts.append(f"<i>Why it matters:</i> {why}")
    if url:
        safe_url = html.escape(url, quote=True)
        parts.append(f'🔗 <a href="{safe_url}">{src_name}</a>')
    return "\n".join(parts)


async def deliver(bot, chat_id, brief: dict) -> None:
    """Send the brief: a header per category, then one message per story."""
    date_str = brief.get("date", "")
    cats = {c["name"]: c for c in config.load_categories()}

    await bot.send_message(
        chat_id=chat_id,
        text=f"📱 <b>Your Daily Brief</b> — {html.escape(date_str)}",
        parse_mode=ParseMode.HTML,
    )

    for cat in brief.get("categories", []):
        name = cat.get("name", "")
        emoji = cats.get(name, {}).get("emoji", "•")
        await bot.send_message(
            chat_id=chat_id,
            text=f"\n{emoji} <b>{html.escape(name.upper())}</b>",
            parse_mode=ParseMode.HTML,
        )
        for story in cat.get("stories", []):
            await bot.send_message(
                chat_id=chat_id,
                text=_story_html(story),
                parse_mode=ParseMode.HTML,
                reply_markup=_story_markup(story["id"]),
                link_preview_options=_NO_PREVIEW,
            )

    await bot.send_message(
        chat_id=chat_id,
        text="Rate the stories 👍 / 🤔 / 👎 — I use it to tune tomorrow's brief.",
    )


async def send_brief(bot, chat_id) -> None:
    """Generate, archive, and deliver a brief to one chat."""
    await bot.send_message(chat_id=chat_id, text="🔎 Researching today's brief…")
    try:
        profile = preferences.build_profile()
        brief = await asyncio.to_thread(curator.generate_brief, profile)
        curator.save_archive(brief)
        await deliver(bot, chat_id, brief)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the user
        log.exception("Failed to build brief")
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Couldn't build the brief this time: {html.escape(str(exc))}",
            parse_mode=ParseMode.HTML,
        )


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 I'm your daily news bot.\n\n"
        "• I send a categorized brief every morning.\n"
        "• Tap 👍 / 👎 on each story so I learn what you like.\n\n"
        "Commands:\n"
        "/brief — get a brief right now\n"
        "/chatid — show this chat's ID (put it in .env as TELEGRAM_CHAT_ID)"
    )


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"This chat's ID is: {update.effective_chat.id}\n"
        "Set TELEGRAM_CHAT_ID to this in your .env, then restart the bot."
    )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_brief(context.bot, update.effective_chat.id)


async def on_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        _, vote, story_id = query.data.split("|", 2)
    except ValueError:
        await query.answer("Unrecognized button.")
        return
    if vote not in _VOTES:
        await query.answer("Unrecognized vote.")
        return

    story = curator.find_story(story_id)
    if story is None:
        # Fall back to a minimal record so the vote still counts.
        story = {"id": story_id, "category": "", "headline": "", "source_url": ""}
    preferences.record_rating(story, vote)

    label = _VOTES[vote][1]
    await query.answer(label)
    # Replace the buttons with a confirmation so it's clear the vote registered.
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"✓ {label}", callback_data="noop")]]
        )
    )


async def on_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_brief(context.bot, context.job.chat_id)


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #
def _parse_chat_id(value: str) -> int | None:
    """Return the chat id as an int, or None if it isn't a valid numeric id.

    Telegram chat ids are integers (channels/groups can be negative). A bot
    username like 'interestingest_bot' is NOT a chat id."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def main() -> None:
    missing = config.missing_required()
    if missing:
        raise SystemExit(
            "Missing required settings: "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill them in."
        )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CallbackQueryHandler(on_noop, pattern=r"^noop$"))
    app.add_handler(CallbackQueryHandler(on_rating, pattern=r"^v\|"))

    chat_id = _parse_chat_id(config.TELEGRAM_CHAT_ID)
    if chat_id is not None:
        tz = ZoneInfo(config.TIMEZONE)
        app.job_queue.run_daily(
            daily_job,
            time=dt.time(config.BRIEF_HOUR, config.BRIEF_MINUTE, tzinfo=tz),
            chat_id=chat_id,
            name="daily_brief",
        )
        log.info(
            "Daily brief scheduled for %02d:%02d %s -> chat %s",
            config.BRIEF_HOUR,
            config.BRIEF_MINUTE,
            config.TIMEZONE,
            chat_id,
        )
    elif config.TELEGRAM_CHAT_ID:
        log.warning(
            "TELEGRAM_CHAT_ID is %r, which is not a numeric chat ID — no daily "
            "schedule set. Message your bot in Telegram and send /chatid to get "
            "the number, put THAT in .env, and restart. /brief still works now.",
            config.TELEGRAM_CHAT_ID,
        )
    else:
        log.warning(
            "TELEGRAM_CHAT_ID not set — no daily schedule. "
            "Send /chatid in Telegram, add the number to .env, and restart. "
            "/brief still works now."
        )

    log.info("Bot starting (model=%s). Press Ctrl+C to stop.", config.MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
