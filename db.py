from __future__ import annotations

import asyncio
import os
import secrets
from datetime import date, datetime, timedelta, timezone

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


def _get_or_create_user_sync(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    referrer_telegram_id: int | None = None,
) -> dict:
    db = get_client()
    existing = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    if existing.data:
        user = existing.data[0]
        user["_is_new"] = False
        return user

    row = {"telegram_id": telegram_id, "username": username, "first_name": first_name}
    referrer = None
    if referrer_telegram_id and referrer_telegram_id != telegram_id:
        ref_rows = db.table("users").select("id").eq("telegram_id", referrer_telegram_id).execute().data
        if ref_rows:
            referrer = ref_rows[0]
            row["referred_by"] = referrer["id"]

    created = db.table("users").insert(row).execute().data[0]
    if referrer:
        _grant_referral_bonus_sync(created["id"], referrer["id"])
        created = db.table("users").select("*").eq("id", created["id"]).execute().data[0]

    created["_is_new"] = True
    return created


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    referrer_telegram_id: int | None = None,
) -> dict:
    return await _run(_get_or_create_user_sync, telegram_id, username, first_name, referrer_telegram_id)


def _grant_referral_bonus_sync(referee_id: str, referrer_id: str) -> None:
    db = get_client()
    now = datetime.now(timezone.utc)

    db.table("users").update(
        {"tier": "pro", "tier_expires_at": (now + timedelta(days=3)).isoformat()}
    ).eq("id", referee_id).execute()

    referrer = db.table("users").select("tier, tier_expires_at").eq("id", referrer_id).execute().data[0]
    tier = referrer.get("tier") or "free"
    base = now
    if tier in ("pro", "ultra") and referrer.get("tier_expires_at"):
        try:
            exp_dt = datetime.fromisoformat(referrer["tier_expires_at"].replace("Z", "+00:00"))
            if exp_dt > now:
                base = exp_dt
        except ValueError:
            pass
    if tier not in ("pro", "ultra"):
        tier = "pro"
    db.table("users").update(
        {"tier": tier, "tier_expires_at": (base + timedelta(days=5)).isoformat()}
    ).eq("id", referrer_id).execute()


def _count_referrals_sync(user_id: str) -> int:
    result = get_client().table("users").select("id", count="exact").eq("referred_by", user_id).execute()
    return result.count or 0


async def count_referrals(user_id: str) -> int:
    return await _run(_count_referrals_sync, user_id)


def effective_tier(user: dict) -> str:
    """Tier accounting for expiration — a lapsed pro/ultra reads back as free
    without needing a write, so callers never have to think about cleanup."""
    tier = user.get("tier") or "free"
    if tier == "free":
        return "free"
    expires_at = user.get("tier_expires_at")
    if not expires_at:
        return tier
    try:
        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return tier
    return "free" if exp_dt <= datetime.now(timezone.utc) else tier


def _grant_tier_sync(user_id: str, tier: str, days: int | None) -> dict:
    db = get_client()
    now = datetime.now(timezone.utc)
    if days is None:
        expires_at = None
    else:
        existing = db.table("users").select("tier, tier_expires_at").eq("id", user_id).execute().data[0]
        base = now
        if existing.get("tier") == tier and existing.get("tier_expires_at"):
            try:
                exp_dt = datetime.fromisoformat(existing["tier_expires_at"].replace("Z", "+00:00"))
                if exp_dt > now:
                    base = exp_dt
            except ValueError:
                pass
        expires_at = (base + timedelta(days=days)).isoformat()
    return (
        db.table("users")
        .update({"tier": tier, "tier_expires_at": expires_at})
        .eq("id", user_id)
        .execute()
        .data[0]
    )


async def grant_tier(user_id: str, tier: str, days: int | None) -> dict:
    return await _run(_grant_tier_sync, user_id, tier, days)


def _downgrade_expired_users_sync() -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    get_client().table("users").update({"tier": "free", "tier_expires_at": None}).neq(
        "tier", "free"
    ).lt("tier_expires_at", now_iso).execute()


async def downgrade_expired_users() -> None:
    await _run(_downgrade_expired_users_sync)


def _create_order_sync(user_id: str, tier: str, period: str, amount: float) -> dict:
    return (
        get_client()
        .table("orders")
        .insert({"user_id": user_id, "tier": tier, "period": period, "amount": amount, "status": "pending"})
        .execute()
        .data[0]
    )


async def create_order(user_id: str, tier: str, period: str, amount: float) -> dict:
    return await _run(_create_order_sync, user_id, tier, period, amount)


def _set_order_transaction_sync(order_id: str, transaction_id: str) -> None:
    get_client().table("orders").update({"transaction_id": transaction_id}).eq("id", order_id).execute()


async def set_order_transaction(order_id: str, transaction_id: str) -> None:
    await _run(_set_order_transaction_sync, order_id, transaction_id)


def _get_order_by_transaction_sync(transaction_id: str) -> dict | None:
    rows = (
        get_client()
        .table("orders")
        .select("*, users(id, telegram_id)")
        .eq("transaction_id", transaction_id)
        .execute()
        .data
    )
    return rows[0] if rows else None


async def get_order_by_transaction(transaction_id: str) -> dict | None:
    return await _run(_get_order_by_transaction_sync, transaction_id)


def _mark_order_status_sync(order_id: str, status: str) -> None:
    fields = {"status": status}
    if status == "confirmed":
        fields["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    get_client().table("orders").update(fields).eq("id", order_id).execute()


async def mark_order_status(order_id: str, status: str) -> None:
    await _run(_mark_order_status_sync, order_id, status)


def _get_user_by_quick_secret_sync(secret: str) -> dict | None:
    rows = get_client().table("users").select("*").eq("quick_secret", secret).execute().data
    return rows[0] if rows else None


async def get_user_by_quick_secret(secret: str) -> dict | None:
    return await _run(_get_user_by_quick_secret_sync, secret)


def _get_or_create_quick_secret_sync(user_id: str) -> str:
    db = get_client()
    row = db.table("users").select("quick_secret").eq("id", user_id).execute().data[0]
    if row.get("quick_secret"):
        return row["quick_secret"]
    secret = secrets.token_hex(24)
    db.table("users").update({"quick_secret": secret}).eq("id", user_id).execute()
    return secret


async def get_or_create_quick_secret(user_id: str) -> str:
    return await _run(_get_or_create_quick_secret_sync, user_id)


def _check_and_increment_quota_sync(user: dict) -> bool:
    """Returns True if the action is allowed (and records it), False if quota exceeded."""
    limit = TIER_DAILY_LIMITS.get(effective_tier(user), FREE_DAILY_AI_LIMIT)
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
        .select("*, users(telegram_id, tz_offset)")
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


def _set_user_tz_offset_sync(user_id: str, tz_offset: int):
    get_client().table("users").update({"tz_offset": tz_offset}).eq("id", user_id).execute()


async def set_user_tz_offset(user_id: str, tz_offset: int):
    await _run(_set_user_tz_offset_sync, user_id, tz_offset)


def _get_tasks_needing_reminder_sync(now_iso: str) -> list[dict]:
    """Any task due by now and not yet reminded — open-ended so a missed cron
    tick (Render cold start) still catches up instead of skipping the reminder."""
    return (
        get_client()
        .table("tasks")
        .select("*, users(telegram_id)")
        .eq("remind", True)
        .eq("reminded", False)
        .lte("due_at", now_iso)
        .execute()
        .data
    )


async def get_tasks_needing_reminder(now_iso: str) -> list[dict]:
    return await _run(_get_tasks_needing_reminder_sync, now_iso)


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


def _get_meetings_needing_reminder_sync(field: str, now_iso: str, threshold_iso: str) -> list[dict]:
    """Meetings that haven't started yet but are due for this reminder (starts_at
    within the lead window from now) — open lower bound so a missed tick still
    catches up, upper bound so we never remind about a meeting already past."""
    db = get_client()
    meetings = (
        db.table("meetings")
        .select("*, users(telegram_id)")
        .eq(field, False)
        .gt("starts_at", now_iso)
        .lte("starts_at", threshold_iso)
        .execute()
        .data
    )
    return meetings


async def get_meetings_needing_reminder(field: str, now_iso: str, threshold_iso: str) -> list[dict]:
    return await _run(_get_meetings_needing_reminder_sync, field, now_iso, threshold_iso)


def _mark_meeting_reminded_sync(meeting_id: str, field: str):
    get_client().table("meetings").update({field: True}).eq("id", meeting_id).execute()


async def mark_meeting_reminded(meeting_id: str, field: str):
    await _run(_mark_meeting_reminded_sync, meeting_id, field)
