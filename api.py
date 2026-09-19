from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import parse_qsl

from aiohttp import web
from aiohttp_cors import ResourceOptions, setup as cors_setup

import db

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
    return web.json_response({"user": {"is_pro": user["is_pro"]}, "digest": digest})


_LIST_FNS = {
    "tasks": db.list_tasks,
    "notes": db.list_notes,
    "meetings": db.list_meetings,
    "money": db.list_money,
    "food": db.list_food,
    "rituals": db.list_rituals,
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
