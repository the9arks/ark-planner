from __future__ import annotations

from datetime import datetime, timedelta, timezone

import db
import payments
from core import send_message as _send_message

UTC = timezone.utc

_TARIFFS_KEYBOARD = {"inline_keyboard": [[{"text": "💳 Тарифы", "callback_data": "info_tariffs"}]]}

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _user_now(user: dict) -> datetime:
    return datetime.now(timezone(timedelta(hours=user.get("tz_offset", 3))))


def _parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = value.split(":")[:2]
    return int(hh), int(mm)


def _due(now: datetime, hour: int, minute: int) -> bool:
    """Target time has passed today — open-ended (no upper bound) so a missed
    cron tick (Render free-tier cold start) still catches up later in the day
    instead of silently skipping the reminder for good."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= target


async def _send_morning_digests(_unused_now: datetime):
    for user in await db.get_all_users():
        time_value = user.get("morning_digest_time")
        if not time_value:
            continue  # user turned this reminder off
        now = _user_now(user)
        today_iso = now.date().isoformat()
        hour, minute = _parse_hhmm(time_value)
        if not _due(now, hour, minute):
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
            time_value = user.get(time_field)
            if not time_value:
                continue  # user turned this reminder off
            now = _user_now(user)
            today_iso = now.date().isoformat()
            hour, minute = _parse_hhmm(time_value)
            if not _due(now, hour, minute):
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


async def _send_money_reminders(_unused_now: datetime):
    for user in await db.get_all_users():
        time_value = user.get("money_reminder_time")
        if not time_value:
            continue  # user turned this reminder off
        now = _user_now(user)
        today_iso = now.date().isoformat()
        hour, minute = _parse_hhmm(time_value)
        if not _due(now, hour, minute):
            continue
        if user.get("last_money_reminder_date") == today_iso:
            continue
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        if await db.has_money_entry_since(user["id"], since):
            continue
        await _send_message(
            user["telegram_id"],
            "Не забыл занести траты за сегодня? Скинь чек или просто напиши сумму.",
        )
        await db.mark_money_reminder_sent(user["id"], today_iso)


async def _send_meeting_reminders(now: datetime):
    for field, delta_minutes, label in (
        ("reminded_2h", 120, "через 2 часа"),
        ("reminded_30m", 30, "через 30 минут"),
    ):
        now_iso = now.isoformat()
        threshold_iso = (now + timedelta(minutes=delta_minutes)).isoformat()
        meetings = await db.get_meetings_needing_reminder(field, now_iso, threshold_iso)
        for m in meetings:
            telegram_id = (m.get("users") or {}).get("telegram_id")
            if not telegram_id:
                continue
            who = f" с {m['with_who']}" if m.get("with_who") else ""
            await _send_message(telegram_id, f"🔔 Встреча{who} {label}")
            await db.mark_meeting_reminded(m["id"], field)


async def _send_task_reminders(now: datetime):
    tasks = await db.get_tasks_needing_reminder(now.isoformat())
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
        if now < remind_at or now >= start_dt:
            continue
        await _send_message(
            telegram_id,
            f"🔔 «{habit['title']}» в {habit['start_time'][:5]} (через {lead} мин)",
        )
        await db.mark_habit_reminded(habit["id"], today_iso)


async def _send_last_day_warnings(now: datetime):
    threshold = now + timedelta(hours=24)
    users = await db.get_users_needing_last_day_warning(now.isoformat(), threshold.isoformat())
    for user in users:
        tier_label = payments.TIER_LABEL.get(user["tier"], user["tier"])
        await _send_message(
            user["telegram_id"],
            f"⏳ Завтра заканчивается твоя подписка {tier_label}. Чтобы не потерять доступ — "
            f"продли сейчас, это займёт минуту.",
            reply_markup=_TARIFFS_KEYBOARD,
        )
        await db.mark_last_day_notified(user["id"], user["tier_expires_at"])


async def _send_expired_notifications(now: datetime):
    downgraded = await db.downgrade_expired_users()
    for user in downgraded:
        tier_label = payments.TIER_LABEL.get(user["tier"], user["tier"])
        await _send_message(
            user["telegram_id"],
            f"😔 Подписка {tier_label} закончилась — аккаунт переведён на Free. "
            f"Хочешь вернуть безлимит и историю — оформи новую подписку.",
            reply_markup=_TARIFFS_KEYBOARD,
        )


async def run_tick():
    now = datetime.now(UTC)
    await _send_last_day_warnings(now)
    await _send_expired_notifications(now)
    await _send_morning_digests(now)
    await _send_meal_reminders(now)
    await _send_money_reminders(now)
    await _send_meeting_reminders(now)
    await _send_habit_reminders(now)
    await _send_task_reminders(now)
