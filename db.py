from __future__ import annotations

import asyncio
import os
from datetime import date

from supabase import Client, create_client

_client: Client | None = None

TIER_DAILY_LIMITS = {"free": 3, "pro": 20, "ultra": None}
FREE_DAILY_AI_LIMIT = TIER_DAILY_LIMITS["free"]


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    return _client


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _get_or_create_user_sync(telegram_id: int, username: str | None, first_name: str | None) -> dict:
    db = get_client()
    existing = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    if existing.data:
        return existing.data[0]
    created = db.table("users").insert(
        {"telegram_id": telegram_id, "username": username, "first_name": first_name}
    ).execute()
    return created.data[0]


async def get_or_create_user(telegram_id: int, username: str | None, first_name: str | None) -> dict:
    return await _run(_get_or_create_user_sync, telegram_id, username, first_name)


def _check_and_increment_quota_sync(user: dict) -> bool:
    """Returns True if the action is allowed (and records it), False if quota exceeded."""
    limit = TIER_DAILY_LIMITS.get(user.get("tier") or "free", FREE_DAILY_AI_LIMIT)
    if limit is None:
        return True

    db = get_client()
    today = date.today().isoformat()
    row = (
        db.table("ai_usage")
        .select("*")
        .eq("user_id", user["id"])
        .eq("action_date", today)
        .execute()
    )
    count = row.data[0]["count"] if row.data else 0
    if count >= limit:
        return False

    if row.data:
        db.table("ai_usage").update({"count": count + 1}).eq("user_id", user["id"]).eq(
            "action_date", today
        ).execute()
    else:
        db.table("ai_usage").insert(
            {"user_id": user["id"], "action_date": today, "count": 1}
        ).execute()
    return True


async def check_and_increment_quota(user: dict) -> bool:
    return await _run(_check_and_increment_quota_sync, user)


def _insert_sync(table: str, row: dict) -> dict:
    result = get_client().table(table).insert(row).execute()
    return result.data[0]


async def add_task(user_id: str, title: str, due_at: str | None = None, remind: bool = False) -> dict:
    return await _run(
        _insert_sync,
        "tasks",
        {"user_id": user_id, "title": title, "due_at": due_at, "remind": remind},
    )


async def add_note(user_id: str, content: str) -> dict:
    return await _run(_insert_sync, "notes", {"user_id": user_id, "content": content})


async def add_meeting(user_id: str, title: str, with_who: str | None, starts_at: str | None) -> dict:
    return await _run(
        _insert_sync,
        "meetings",
        {"user_id": user_id, "title": title, "with_who": with_who, "starts_at": starts_at},
    )


async def add_money(user_id: str, amount: float, category: str | None, comment: str | None, ai_comment: str | None) -> dict:
    return await _run(
        _insert_sync,
        "money_entries",
        {
            "user_id": user_id,
            "amount": amount,
            "category": category,
            "comment": comment,
            "ai_comment": ai_comment,
        },
    )


async def add_food(user_id: str, description: str | None, calories: int | None, protein_g: float | None, fat_g: float | None, carbs_g: float | None) -> dict:
    return await _run(
        _insert_sync,
        "food_entries",
        {
            "user_id": user_id,
            "description": description,
            "calories": calories,
            "protein_g": protein_g,
            "fat_g": fat_g,
            "carbs_g": carbs_g,
        },
    )


async def add_ritual_log(user_id: str, title: str) -> dict:
    db = get_client()

    def _sync():
        existing = (
            db.table("rituals").select("*").eq("user_id", user_id).eq("title", title).execute()
        )
        if existing.data:
            ritual = existing.data[0]
        else:
            ritual = db.table("rituals").insert({"user_id": user_id, "title": title}).execute().data[0]
        return db.table("ritual_logs").insert(
            {"ritual_id": ritual["id"], "user_id": user_id}
        ).execute().data[0]

    return await _run(_sync)


def _upsert_habit_sync(
    user_id: str,
    title: str,
    days_of_week: list[str] | None,
    start_time: str | None,
    reminder_lead_minutes: int | None,
    habit_type: str,
) -> dict:
    db = get_client()
    row = {
        "user_id": user_id,
        "title": title,
        "days_of_week": days_of_week,
        "start_time": start_time,
        "reminder_lead_minutes": reminder_lead_minutes,
        "habit_type": habit_type,
        "is_habit": True,
    }
    existing = db.table("rituals").select("*").eq("user_id", user_id).eq("title", title).execute()
    if existing.data:
        return (
            db.table("rituals")
            .update(row)
            .eq("id", existing.data[0]["id"])
            .execute()
            .data[0]
        )
    row["streak_start_date"] = date.today().isoformat()
    return db.table("rituals").insert(row).execute().data[0]


async def upsert_habit(
    user_id: str,
    title: str,
    days_of_week: list[str] | None,
    start_time: str | None,
    reminder_lead_minutes: int | None,
    habit_type: str = "build",
) -> dict:
    return await _run(
        _upsert_habit_sync,
        user_id,
        title,
        days_of_week,
        start_time,
        reminder_lead_minutes,
        habit_type,
    )


def _find_habit_sync(user_id: str, title_hint: str) -> dict | None:
    habits = (
        get_client()
        .table("rituals")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_habit", True)
        .execute()
        .data
    )
    hint = (title_hint or "").strip().lower()
    if not hint:
        return None
    for h in habits:
        t = (h.get("title") or "").strip().lower()
        if t and (t in hint or hint in t):
            return h
    return None


async def find_habit(user_id: str, title_hint: str) -> dict | None:
    return await _run(_find_habit_sync, user_id, title_hint)


def _reset_habit_streak_sync(habit_id: str, today_iso: str):
    get_client().table("rituals").update({"streak_start_date": today_iso}).eq(
        "id", habit_id
    ).execute()


async def reset_habit_streak(habit_id: str, today_iso: str):
    await _run(_reset_habit_streak_sync, habit_id, today_iso)


def _list_habits_sync(user_id: str) -> list[dict]:
    return (
        get_client()
        .table("rituals")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_habit", True)
        .execute()
        .data
    )


async def list_habits(user_id: str) -> list[dict]:
    return await _run(_list_habits_sync, user_id)


def _get_all_habits_sync() -> list[dict]:
    return (
        get_client()
        .table("rituals")
        .select("*, users(telegram_id)")
        .eq("is_habit", True)
        .not_.is_("start_time", "null")
        .execute()
        .data
    )


async def get_all_habits() -> list[dict]:
    return await _run(_get_all_habits_sync)


def _mark_habit_reminded_sync(ritual_id: str, today_iso: str):
    get_client().table("rituals").update({"last_reminded_date": today_iso}).eq(
        "id", ritual_id
    ).execute()


async def mark_habit_reminded(ritual_id: str, today_iso: str):
    await _run(_mark_habit_reminded_sync, ritual_id, today_iso)


def _set_user_time_sync(user_id: str, field: str, time_str: str):
    get_client().table("users").update({field: time_str}).eq("id", user_id).execute()


async def set_user_time(user_id: str, field: str, time_str: str):
    await _run(_set_user_time_sync, user_id, field, time_str)


def _get_tasks_needing_reminder_sync(window_start: str, window_end: str) -> list[dict]:
    return (
        get_client()
        .table("tasks")
        .select("*, users(telegram_id)")
        .eq("remind", True)
        .eq("reminded", False)
        .gte("due_at", window_start)
        .lt("due_at", window_end)
        .execute()
        .data
    )


async def get_tasks_needing_reminder(window_start: str, window_end: str) -> list[dict]:
    return await _run(_get_tasks_needing_reminder_sync, window_start, window_end)


def _mark_task_reminded_sync(task_id: str):
    get_client().table("tasks").update({"reminded": True}).eq("id", task_id).execute()


async def mark_task_reminded(task_id: str):
    await _run(_mark_task_reminded_sync, task_id)


def _get_digest_sync(user_id: str) -> dict:
    db = get_client()
    today = date.today().isoformat()

    def count(table: str, extra=None):
        q = db.table(table).select("id", count="exact").eq("user_id", user_id).gte(
            "created_at", today
        )
        return q.execute().count or 0

    return {
        "tasks_today": count("tasks"),
        "notes_today": count("notes"),
        "meetings_today": count("meetings"),
        "money_today": count("money_entries"),
        "food_today": count("food_entries"),
    }


async def get_digest(user_id: str) -> dict:
    return await _run(_get_digest_sync, user_id)


def _list_sync(table: str, user_id: str, limit: int) -> list[dict]:
    result = (
        get_client()
        .table(table)
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


async def list_tasks(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "tasks", user_id, limit)


async def list_notes(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "notes", user_id, limit)


async def list_meetings(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "meetings", user_id, limit)


async def list_money(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "money_entries", user_id, limit)


async def list_food(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "food_entries", user_id, limit)


async def list_rituals(user_id: str, limit: int = 50) -> list[dict]:
    return await _run(_list_sync, "ritual_logs", user_id, limit)


def _get_all_users_sync() -> list[dict]:
    return get_client().table("users").select("*").execute().data


async def get_all_users() -> list[dict]:
    return await _run(_get_all_users_sync)


def _get_today_agenda_sync(user_id: str) -> dict:
    db = get_client()
    today = date.today().isoformat()
    tomorrow = (date.today().toordinal() + 1)
    from datetime import date as _date

    tomorrow_iso = _date.fromordinal(tomorrow).isoformat()

    meetings = (
        db.table("meetings")
        .select("*")
        .eq("user_id", user_id)
        .gte("starts_at", today)
        .lt("starts_at", tomorrow_iso)
        .order("starts_at")
        .execute()
        .data
    )
    tasks = (
        db.table("tasks")
        .select("*")
        .eq("user_id", user_id)
        .eq("done", False)
        .gte("due_at", today)
        .lt("due_at", tomorrow_iso)
        .order("due_at")
        .execute()
        .data
    )
    return {"meetings": meetings, "tasks": tasks}


async def get_today_agenda(user_id: str) -> dict:
    return await _run(_get_today_agenda_sync, user_id)


def _has_food_entry_since_sync(user_id: str, since_iso: str) -> bool:
    result = (
        get_client()
        .table("food_entries")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", since_iso)
        .execute()
    )
    return (result.count or 0) > 0


async def has_food_entry_since(user_id: str, since_iso: str) -> bool:
    return await _run(_has_food_entry_since_sync, user_id, since_iso)


def _mark_date_field_sync(user_id: str, field: str, value: str):
    get_client().table("users").update({field: value}).eq("id", user_id).execute()


async def mark_morning_digest_sent(user_id: str, today_iso: str):
    await _run(_mark_date_field_sync, user_id, "last_morning_digest_date", today_iso)


async def mark_meal_reminder_sent(user_id: str, meal: str, today_iso: str):
    field = f"last_{meal}_reminder_date"
    await _run(_mark_date_field_sync, user_id, field, today_iso)


def _get_meetings_needing_reminder_sync(field: str, window_start: str, window_end: str) -> list[dict]:
    db = get_client()
    meetings = (
        db.table("meetings")
        .select("*, users(telegram_id)")
        .eq(field, False)
        .gte("starts_at", window_start)
        .lt("starts_at", window_end)
        .execute()
        .data
    )
    return meetings


async def get_meetings_needing_reminder(field: str, window_start: str, window_end: str) -> list[dict]:
    return await _run(_get_meetings_needing_reminder_sync, field, window_start, window_end)


def _mark_meeting_reminded_sync(meeting_id: str, field: str):
    get_client().table("meetings").update({field: True}).eq("id", meeting_id).execute()


async def mark_meeting_reminded(meeting_id: str, field: str):
    await _run(_mark_meeting_reminded_sync, meeting_id, field)
