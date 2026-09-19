from __future__ import annotations

import asyncio
import os
from datetime import date

from supabase import Client, create_client

_client: Client | None = None

FREE_DAILY_AI_LIMIT = 3


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
    if user.get("is_pro"):
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
    if count >= FREE_DAILY_AI_LIMIT:
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


async def add_task(user_id: str, title: str, due_at: str | None = None) -> dict:
    return await _run(_insert_sync, "tasks", {"user_id": user_id, "title": title, "due_at": due_at})


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
