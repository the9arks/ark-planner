from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiohttp

import db

UTC = timezone.utc

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _user_now(user: dict) -> datetime:
    return datetime.now(timezone(timedelta(hours=user.get("tz_offset", 3))))


async def _send_message(telegram_id: int, text: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"chat_id": telegram_id, "text": text}) as resp:
            await resp.read()


def _parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = value.split(":")[:2]
    return int(hh), int(mm)


def _in_window(now: datetime, hour: int, minute: int, span_minutes: int = 10) -> bool:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target <= now < target + timedelta(minutes=span_minutes)


async def _send_morning_digests(_unused_now: datetime):
    for user in await db.get_all_users():
        now = _user_now(user)
        today_iso = now.date().isoformat()
        hour, minute = _parse_hhmm(user.get("morning_digest_time") or "08:00")
        if not _in_window(now, hour, minute):
            continue
        if user.get("last_morning_digest_date") == today_iso:
            continue
        agenda = await db.get_today_agenda(user["id"])
        lines = ["Доброе утро! Вот план на сегодня:"]
        if agenda["meetings"]:
            lines.append("\n🤝 Встречи:")
            for m in agenda["meetings"]:
                dt = datetime.fromisoformat(m["starts_at"]).astimezone(now.tzinfo)
                who = f" с {m['with_who']}" if m.get("with_who") else ""
                lines.append(f"  {dt.strftime('%H:%M')}{who}")
        if agenda["tasks"]:
            lines.append("\n✅ Задачи:")
            for t in agenda["tasks"]:
                lines.append(f"  {t['title']}")
        if not agenda["meetings"] and not agenda["tasks"]:
            lines.append("На сегодня ничего не запланировано — можно просто пожить.")
        await _send_message(user["telegram_id"], "\n".join(lines))
        await db.mark_morning_digest_sent(user["id"], today_iso)


# meal -> (user time field, "logged since" hour, reminder field, label)
MEAL_CONFIG = {
    "breakfast": ("breakfast_reminder_time", 0, "позавтракал"),
    "lunch": ("lunch_reminder_time", 11, "пообедал"),
    "dinner": ("dinner_reminder_time", 17, "поужинал"),
}


async def _send_meal_reminders(_unused_now: datetime):
    for meal, (time_field, since_hour, label) in MEAL_CONFIG.items():
        for user in await db.get_all_users():
            now = _user_now(user)
            today_iso = now.date().isoformat()
            hour, minute = _parse_hhmm(user.get(time_field) or "09:30")
            if not _in_window(now, hour, minute):
                continue
            field = f"last_{meal}_reminder_date"
            if user.get(field) == today_iso:
                continue
            since = now.replace(hour=since_hour, minute=0, second=0, microsecond=0).isoformat()
            if await db.has_food_entry_since(user["id"], since):
                continue
            await _send_message(
                user["telegram_id"],
                f"Уже {label}? Скинь фото тарелки или напиши, что съел — посчитаю калории.",
            )
            await db.mark_meal_reminder_sent(user["id"], meal, today_iso)


async def _send_meeting_reminders(now: datetime):
    for field, delta_minutes, label in (
        ("reminded_2h", 120, "через 2 часа"),
        ("reminded_30m", 30, "через 30 минут"),
    ):
        window_start = (now + timedelta(minutes=delta_minutes - 5)).isoformat()
        window_end = (now + timedelta(minutes=delta_minutes + 5)).isoformat()
        meetings = await db.get_meetings_needing_reminder(field, window_start, window_end)
        for m in meetings:
            telegram_id = (m.get("users") or {}).get("telegram_id")
            if not telegram_id:
                continue
            who = f" с {m['with_who']}" if m.get("with_who") else ""
            await _send_message(telegram_id, f"🔔 Встреча{who} {label}")
            await db.mark_meeting_reminded(m["id"], field)


async def _send_task_reminders(now: datetime):
    window_start = (now - timedelta(minutes=5)).isoformat()
    window_end = (now + timedelta(minutes=5)).isoformat()
    tasks = await db.get_tasks_needing_reminder(window_start, window_end)
    for t in tasks:
        telegram_id = (t.get("users") or {}).get("telegram_id")
        if not telegram_id:
            continue
        await _send_message(telegram_id, f"🔔 {t['title']}")
        await db.mark_task_reminded(t["id"])


async def _send_habit_reminders(_unused_now: datetime):
    for habit in await db.get_all_habits():
        habit_user = habit.get("users") or {}
        telegram_id = habit_user.get("telegram_id")
        if not telegram_id:
            continue
        now = datetime.now(timezone(timedelta(hours=habit_user.get("tz_offset", 3))))
        today_iso = now.date().isoformat()
        today_code = WEEKDAY_CODES[now.weekday()]

        if habit.get("last_reminded_date") == today_iso:
            continue
        days = habit.get("days_of_week") or []
        if today_code not in days:
            continue
        start_hour, start_minute = _parse_hhmm(habit["start_time"])
        start_dt = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        lead = habit.get("reminder_lead_minutes") or 60
        remind_at = start_dt - timedelta(minutes=lead)
        if not (remind_at <= now < remind_at + timedelta(minutes=10)):
            continue
        await _send_message(
            telegram_id,
            f"🔔 «{habit['title']}» в {habit['start_time'][:5]} (через {lead} мин)",
        )
        await db.mark_habit_reminded(habit["id"], today_iso)


async def run_tick():
    now = datetime.now(UTC)
    await _send_morning_digests(now)
    await _send_meal_reminders(now)
    await _send_meeting_reminders(now)
    await _send_habit_reminders(now)
    await _send_task_reminders(now)
