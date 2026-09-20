from __future__ import annotations

import hashlib
import hmac
import logging
import os
from urllib.parse import parse_qsl

from aiohttp import web
from aiohttp_cors import ResourceOptions, setup as cors_setup

import ai
import core
import db
import payments

ALLOW_DEV_AUTH = os.environ.get("ALLOW_DEV_AUTH", "true").lower() == "true"


def _verify_init_data(init_data: str) -> dict | None:
    """Validates Telegram WebApp initData per Telegram's documented algorithm."""
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    return pairs


async def _authenticate(request: web.Request) -> dict | None:
    init_data = request.headers.get("Authorization", "").removeprefix("tma ")
    if init_data:
        verified = _verify_init_data(init_data)
        if verified:
            import json

            user_json = json.loads(verified.get("user", "{}"))
            return await db.get_or_create_user(
                telegram_id=user_json["id"],
                username=user_json.get("username"),
                first_name=user_json.get("first_name"),
            )

    if ALLOW_DEV_AUTH:
        dev_id = request.query.get("tg_id")
        if dev_id:
            return await db.get_or_create_user(
                telegram_id=int(dev_id), username="dev", first_name="Dev"
            )

    return None


routes = web.RouteTableDef()


@routes.get("/api/digest")
async def get_digest(request: web.Request):
    user = await _authenticate(request)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    digest = await db.get_digest(user["id"])
    tier = db.effective_tier(user)
    return web.json_response(
        {
            "user": {
                "tier": tier,
                "daily_ai_limit": db.TIER_DAILY_LIMITS.get(tier),
                "morning_digest_time": user.get("morning_digest_time"),
                "breakfast_reminder_time": user.get("breakfast_reminder_time"),
                "lunch_reminder_time": user.get("lunch_reminder_time"),
                "dinner_reminder_time": user.get("dinner_reminder_time"),
                "tz_offset": user.get("tz_offset", 3),
            },
            "digest": digest,
        }
    )


@routes.post("/api/settings/time")
async def set_time_setting(request: web.Request):
    user = await _authenticate(request)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.json()
    field = body.get("field")
    time_str = body.get("value")

    allowed_fields = {
        "morning_digest_time",
        "breakfast_reminder_time",
        "lunch_reminder_time",
        "dinner_reminder_time",
    }
    if field not in allowed_fields:
        return web.json_response({"error": "invalid_field"}, status=400)

    import re

    if not re.fullmatch(r"[0-2]?\d:[0-5]\d", (time_str or "").strip()):
        return web.json_response({"error": "invalid_time"}, status=400)

    await db.set_user_time(user["id"], field, time_str.strip())
    return web.json_response({"ok": True})


@routes.post("/api/settings/timezone")
async def set_timezone_setting(request: web.Request):
    user = await _authenticate(request)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.json()
    try:
        tz_offset = int(body.get("tz_offset"))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_offset"}, status=400)
    if not -12 <= tz_offset <= 14:
        return web.json_response({"error": "invalid_offset"}, status=400)

    await db.set_user_tz_offset(user["id"], tz_offset)
    return web.json_response({"ok": True})


@routes.post("/api/entries")
async def create_entry(request: web.Request):
    user = await _authenticate(request)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "empty_text"}, status=400)

    if not await db.check_and_increment_quota(user):
        return web.json_response({"error": "quota_exceeded"}, status=429)

    tz_offset = user.get("tz_offset", 3)
    try:
        data = ai.classify_text(text, tz_offset=tz_offset)
        data = await core.store_entry(user["id"], data, tz_offset)
        reply = core.format_reply(data)
    except Exception:
        logging.exception("create_entry failed")
        return web.json_response({"error": "processing_failed"}, status=500)

    return web.json_response({"reply": reply, "entry_type": data.get("entry_type")})


@routes.post("/shortcut/{secret}/entry")
async def shortcut_entry(request: web.Request):
    """Quick-capture endpoint for the iOS Action Button / back-tap Shortcut: it
    dictates text on-device (free, no transcription service needed) and POSTs
    it here directly, skipping the Telegram chat UI entirely."""
    secret = request.match_info["secret"]
    user = await db.get_user_by_quick_secret(secret)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "empty_text"}, status=400)

    if not await db.check_and_increment_quota(user):
        return web.json_response({"error": "quota_exceeded"}, status=429)

    tz_offset = user.get("tz_offset", 3)
    try:
        data = ai.classify_text(text, tz_offset=tz_offset)
        data = await core.store_entry(user["id"], data, tz_offset)
        reply = core.format_reply(data)
    except Exception:
        logging.exception("shortcut_entry failed")
        return web.json_response({"error": "processing_failed"}, status=500)

    telegram_id = user.get("telegram_id")
    if telegram_id:
        await core.send_message(telegram_id, f"⚡️ {reply}")

    return web.json_response({"ok": True, "reply": reply})


_LIST_FNS = {
    "tasks": db.list_tasks,
    "notes": db.list_notes,
    "meetings": db.list_meetings,
    "money": db.list_money,
    "food": db.list_food,
    "rituals": db.list_habits,
}


@routes.get("/api/{section}")
async def get_section(request: web.Request):
    section = request.match_info["section"]
    list_fn = _LIST_FNS.get(section)
    if not list_fn:
        return web.json_response({"error": "not_found"}, status=404)

    user = await _authenticate(request)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)

    items = await list_fn(user["id"])
    return web.json_response({"items": items})


@routes.post("/payments/platega/webhook")
async def platega_webhook(request: web.Request):
    if not payments.verify_webhook_auth(
        request.headers.get("X-MerchantId"), request.headers.get("X-Secret")
    ):
        return web.json_response({"error": "forbidden"}, status=403)

    body = await request.json()
    transaction_id = body.get("id")
    status = body.get("status")
    if not transaction_id or status not in ("CONFIRMED", "CANCELED"):
        return web.json_response({"ok": True})

    order = await db.get_order_by_transaction(transaction_id)
    if not order or order.get("status") != "pending":
        return web.json_response({"ok": True})

    if status == "CONFIRMED":
        await db.mark_order_status(order["id"], "confirmed")
        await db.grant_tier(order["user_id"], order["tier"], payments.PERIOD_DAYS[order["period"]])
        telegram_id = (order.get("users") or {}).get("telegram_id")
        if telegram_id:
            await core.send_message(
                telegram_id,
                f"✅ Оплата получена! Тариф {payments.TIER_LABEL[order['tier']]} "
                f"активирован ({payments.PERIOD_LABEL[order['period']]}). Спасибо! 🙌",
            )
    else:
        await db.mark_order_status(order["id"], "canceled")

    return web.json_response({"ok": True})


@routes.get("/cron/{secret}")
async def cron_tick(request: web.Request):
    if request.match_info["secret"] != os.environ.get("CRON_SECRET"):
        return web.json_response({"error": "forbidden"}, status=403)

    import reminders

    await reminders.run_tick()
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)

    cors = cors_setup(
        app,
        defaults={
            "*": ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*"
            )
        },
    )
    for route in list(app.router.routes()):
        cors.add(route)

    return app
