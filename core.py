"""Shared entry-processing logic used by both the Telegram bot and the Mini App API:
classify -> store -> format a reply. Keeping this in one place means the Mini App
composer and the bot chat behave identically."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import aiohttp

import db


async def send_message(telegram_id: int, text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"chat_id": telegram_id, "text": text}) as resp:
            await resp.read()


# Gates real usage (bot messages + Mini App) behind membership in a Telegram channel.
# Both REQUIRED_CHANNEL_ID (whatever getChatMember accepts — "@username" or numeric
# chat id) and REQUIRED_CHANNEL_URL (the https://t.me/... join link shown to users)
# must be set for the gate to turn on; unset, everyone is treated as subscribed.
REQUIRED_CHANNEL_ID = os.environ.get("REQUIRED_CHANNEL_ID")
REQUIRED_CHANNEL_URL = os.environ.get("REQUIRED_CHANNEL_URL")

_SUBSCRIPTION_CACHE_TTL = 600  # seconds — avoids hammering Telegram's API on every action
_subscription_cache: dict[int, tuple[float, bool]] = {}


def subscription_gate_enabled() -> bool:
    return bool(REQUIRED_CHANNEL_ID and REQUIRED_CHANNEL_URL)


async def is_subscribed(telegram_id: int) -> bool:
    """Checks channel membership via a raw Bot API call (kept separate from aiogram's
    Bot instance so api.py can use it too). Fails OPEN on any error — wrong channel id,
    bot not an admin yet, Telegram hiccup — because a misconfigured gate breaking the
    whole product for every user is far worse than the gate briefly doing nothing."""
    if not subscription_gate_enabled():
        return True

    cached = _subscription_cache.get(telegram_id)
    if cached and time.monotonic() - cached[0] < _SUBSCRIPTION_CACHE_TTL:
        return cached[1]

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/getChatMember"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params={"chat_id": REQUIRED_CHANNEL_ID, "user_id": telegram_id}
            ) as resp:
                data = await resp.json()
    except Exception:
        return True

    if not data.get("ok"):
        return True

    subscribed = data["result"].get("status") not in ("left", "kicked")
    _subscription_cache[telegram_id] = (time.monotonic(), subscribed)
    return subscribed


def clear_subscription_cache(telegram_id: int) -> None:
    _subscription_cache.pop(telegram_id, None)

WEEKDAY_RU = {
    "mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт",
    "fri": "Пт", "sat": "Сб", "sun": "Вс",
}


# Claude returns naive local datetimes ("2026-09-20T15:00:00") in the user's own timezone;
# tag them with that UTC offset before they hit Postgres (which otherwise assumes UTC and
# shifts the wall-clock time when read back).
def _tz_suffix(tz_offset: int) -> str:
    sign = "+" if tz_offset >= 0 else "-"
    return f"{sign}{abs(tz_offset):02d}:00"


def _localize(naive_iso: str | None, tz_offset: int) -> str | None:
    if not naive_iso:
        return None
    if "+" in naive_iso or naive_iso.endswith("Z"):
        return naive_iso
    return naive_iso + _tz_suffix(tz_offset)


def streak_days(streak_start_date: str | None, today) -> int | None:
    if not streak_start_date:
        return None
    start = datetime.fromisoformat(streak_start_date).date()
    return (today - start).days


def _consecutive_days(checkin_dates: set, today) -> int:
    """Consecutive-day streak ending today, or ending yesterday if today hasn't
    been checked in yet (so the streak doesn't drop to 0 the moment midnight
    passes, before the user has had a chance to check in)."""
    day = today
    if day not in checkin_dates:
        day -= timedelta(days=1)
    streak = 0
    while day in checkin_dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


async def compute_habit_streak(habit: dict, tz_offset: int = 3) -> int:
    """"Отказы" (quit habits) track days since the last relapse — no daily
    check-in required, absence of a relapse is the point. "Привычки" (build
    habits) need an actual consecutive run of check-ins, computed from
    ritual_logs, not just elapsed calendar time since the habit was defined."""
    today = datetime.now(timezone(timedelta(hours=tz_offset))).date()
    if habit.get("habit_type") == "quit":
        return streak_days(habit.get("streak_start_date"), today) or 0

    timestamps = await db.get_ritual_log_timestamps(habit["id"])
    checkin_dates = set()
    for ts in timestamps:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        checkin_dates.add(dt.astimezone(timezone(timedelta(hours=tz_offset))).date())
    return _consecutive_days(checkin_dates, today)


async def store_entry(user_id: str, data: dict, tz_offset: int = 3) -> dict:
    entry_type = data.get("entry_type")
    if entry_type == "task":
        await db.add_task(
            user_id,
            data.get("title") or data.get("description"),
            _localize(data.get("starts_at"), tz_offset),
            remind=bool(data.get("remind")),
        )
    elif entry_type == "meeting":
        await db.add_meeting(
            user_id,
            data.get("title") or data.get("description"),
            data.get("with_who"),
            _localize(data.get("starts_at"), tz_offset),
        )
    elif entry_type == "money":
        await db.add_money(
            user_id,
            data.get("amount"),
            data.get("category"),
            data.get("description"),
            data.get("comment"),
        )
    elif entry_type == "food":
        await db.add_food(
            user_id,
            data.get("description"),
            data.get("calories"),
            data.get("protein_g"),
            data.get("fat_g"),
            data.get("carbs_g"),
        )
    elif entry_type == "ritual":
        title = data.get("title") or data.get("description")
        action = data.get("habit_action")

        user_today = datetime.now(timezone(timedelta(hours=tz_offset))).date()

        if action == "relapse":
            habit = await db.find_habit(user_id, title)
            if habit:
                await db.reset_habit_streak(habit["id"], user_today.isoformat())
                data["streak_days"] = 0
        elif action == "define" or (data.get("days_of_week") and data.get("start_time")):
            habit = await db.upsert_habit(
                user_id,
                title,
                data.get("days_of_week"),
                data.get("start_time"),
                data.get("reminder_lead_minutes"),
                data.get("habit_type") or "build",
            )
            data["streak_days"] = await compute_habit_streak(habit, tz_offset)
        elif action == "checkin":
            habit = await db.find_habit(user_id, title)
            await db.add_ritual_log(user_id, habit["title"] if habit else title)
            if habit:
                data["streak_days"] = await compute_habit_streak(habit, tz_offset)
        else:
            await db.add_ritual_log(user_id, title)
    else:
        await db.add_note(user_id, data.get("description") or "")
    return data


async def store_entries(user_id: str, entries: list[dict], tz_offset: int = 3) -> list[dict]:
    """A single message can describe several distinct things at once (a task, a
    money entry, a habit checkin all in one breath) — classify_text/classify_photo
    already split the model's response into one dict per thing; this just stores
    each in turn."""
    return [await store_entry(user_id, entry, tz_offset) for entry in entries]


def format_when(iso_str: str | None, tz_offset: int = 3) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    # dt is naive and already in the user's local time (that's what ai.py
    # produces) — compare against "today" in that same timezone, not the
    # server's own clock (server runs UTC, so anyone at UTC+ offsets would
    # get "завтра" for something that's actually later today, every day
    # during the hours their local date has already rolled over past UTC's).
    today = datetime.now(timezone(timedelta(hours=tz_offset))).date()
    if dt.date() == today:
        return f"сегодня в {dt.strftime('%H:%M')}"
    if dt.date().toordinal() - today.toordinal() == 1:
        return f"завтра в {dt.strftime('%H:%M')}"
    return dt.strftime("%d.%m в %H:%M")


def format_reply(data: dict, tz_offset: int = 3) -> str:
    entry_type = data.get("entry_type")
    if entry_type == "task":
        when = format_when(data.get("starts_at"), tz_offset)
        due = f" (до {when})" if when else ""
        reply = f"✅ Задача: {data.get('title') or data.get('description')}{due}"
        if data.get("remind") and when:
            reply += f"\n🔔 Напомню {when}"
    elif entry_type == "meeting":
        when = format_when(data.get("starts_at"), tz_offset)
        when_str = f" {when}" if when else ""
        with_who = f" с {data['with_who']}" if data.get("with_who") else ""
        reply = f"🤝 Встреча{with_who}{when_str}"
    elif entry_type == "money":
        reply = f"💸 Записал: {data.get('amount')}₽ — {data.get('category') or data.get('description')}"
    elif entry_type == "food":
        reply = f"🍽 Записал: {data.get('description')} (~{data.get('calories')} ккал)"
    elif entry_type == "ritual":
        title = data.get("title") or data.get("description")
        action = data.get("habit_action")
        streak = data.get("streak_days")

        if action == "relapse":
            reply = f"Бывает 💪 «{title}»: начинаем стрик заново — сегодня день 0."
        elif action == "define" and data.get("days_of_week") and data.get("start_time"):
            days = ", ".join(WEEKDAY_RU.get(d, d) for d in data["days_of_week"])
            lead = data.get("reminder_lead_minutes") or 60
            reply = (
                f"🔁 Привычка настроена: «{title}»\n"
                f"{days}, в {data['start_time'][:5]}, напомню за {lead} мин"
            )
        elif action == "define":
            kind = "Бросаем" if data.get("habit_type") == "quit" else "Начинаем"
            reply = f"🎯 {kind}: «{title}». Пиши сюда о прогрессе — буду считать дни."
        elif action == "checkin":
            streak_str = f" · день {streak}" if streak is not None else ""
            reply = f"✅ «{title}»{streak_str} — так держать."
        else:
            reply = f"🔁 Ритуал: {title}"
    else:
        reply = f"📝 Записал: {data.get('description')}"

    comment = data.get("comment")
    if comment:
        reply += f"\n\n{comment}"
    return reply


def format_replies(entries: list[dict], tz_offset: int = 3) -> str:
    if len(entries) == 1:
        return format_reply(entries[0], tz_offset)
    return "\n\n".join(f"{i}. {format_reply(e, tz_offset)}" for i, e in enumerate(entries, start=1))
