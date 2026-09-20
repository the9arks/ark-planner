"""Shared entry-processing logic used by both the Telegram bot and the Mini App API:
classify -> store -> format a reply. Keeping this in one place means the Mini App
composer and the bot chat behave identically."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiohttp

import db


async def send_message(telegram_id: int, text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"chat_id": telegram_id, "text": text}) as resp:
            await resp.read()

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
            data["streak_days"] = streak_days(habit.get("streak_start_date"), user_today)
        elif action == "checkin":
            habit = await db.find_habit(user_id, title)
            await db.add_ritual_log(user_id, habit["title"] if habit else title)
            if habit:
                data["streak_days"] = streak_days(habit.get("streak_start_date"), user_today)
        else:
            await db.add_ritual_log(user_id, title)
    else:
        await db.add_note(user_id, data.get("description") or "")
    return data


def format_when(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    today = datetime.now(dt.tzinfo).date() if dt.tzinfo else datetime.now().date()
    if dt.date() == today:
        return f"сегодня в {dt.strftime('%H:%M')}"
    if dt.date().toordinal() - today.toordinal() == 1:
        return f"завтра в {dt.strftime('%H:%M')}"
    return dt.strftime("%d.%m в %H:%M")


def format_reply(data: dict) -> str:
    entry_type = data.get("entry_type")
    if entry_type == "task":
        when = format_when(data.get("starts_at"))
        due = f" (до {when})" if when else ""
        reply = f"✅ Задача: {data.get('title') or data.get('description')}{due}"
        if data.get("remind") and when:
            reply += f"\n🔔 Напомню {when}"
    elif entry_type == "meeting":
        when = format_when(data.get("starts_at"))
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
