from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiohttp

import db

MOSCOW_TZ = timezone(timedelta(hours=3))


async def _send_message(telegram_id: int, text: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"chat_id": telegram_id, "text": text}) as resp:
            await resp.read()


def _in_window(now: datetime, hour: int, minute: int, span_minutes: int = 10) -> bool:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target <= now < target + timedelta(minutes=span_minutes)


async def _send_morning_digests(now: datetime):
    if not _in_window(now, 8, 0):
        return
    today_iso = now.date().isoformat()
    for user in await db.get_all_users():
        if user.get("last_morning_digest_date") == today_iso:
            continue
        agenda = await db.get_today_agenda(user["id"])
        lines = ["Доброе утро! Вот план на сегодня:"]
        if agenda["meetings"]:
            lines.append("\n🤝 Встречи:")
            for m in agenda["meetings"]:
                dt = datetime.fromisoformat(m["starts_at"]).astimezone(MOSCOW_TZ)
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


# meal -> (reminder hour, reminder minute, "logged since" hour)
MEAL_WINDOWS = {
    "breakfast": (9, 30, 0),
    "lunch": (13, 30, 11),
    "dinner": (19, 30, 17),
}
MEAL_LABELS = {
    "breakfast": "позавтракал",
    "lunch": "пообедал",
    "dinner": "поужинал",
}


async def _send_meal_reminders(now: datetime):
    today_iso = now.date().isoformat()
    for meal, (hour, minute, since_hour) in MEAL_WINDOWS.items():
        if not _in_window(now, hour, minute):
            continue
        since = now.replace(hour=since_hour, minute=0, second=0, microsecond=0).isoformat()
        for user in await db.get_all_users():
            field = f"last_{meal}_reminder_date"
            if user.get(field) == today_iso:
                continue
            if await db.has_food_entry_since(user["id"], since):
                continue
            await _send_message(
                user["telegram_id"],
                f"Уже {MEAL_LABELS[meal]}? Скинь фото тарелки или напиши, что съел — посчитаю калории.",
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


async def run_tick():
    now = datetime.now(MOSCOW_TZ)
    await _send_morning_digests(now)
    await _send_meal_reminders(now)
    await _send_meeting_reminders(now)
