from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

import ai
import db

load_dotenv()

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

WELCOME = """\
Привет! Я ARK PLANNER — твой трекер жизни.

Просто пиши мне что происходит: "купить молоко завтра", "завтра в 15:00 встреча с Андреем", \
"потратил 500 на такси", "съел борщ" — я сам разберусь, куда это записать: задачи, встречи, \
деньги, еда, заметки или ритуалы.

Можно присылать фото:
• чек — занесу трату
• тарелка с едой — прикину калории и БЖУ

Бесплатно — {limit} AI-действия в день. Дальше нужен Pro.

Команда /summary — сводка за сегодня.
""".format(limit=db.FREE_DAILY_AI_LIMIT)

QUOTA_EXCEEDED = (
    "На сегодня бесплатные AI-действия закончились "
    f"({db.FREE_DAILY_AI_LIMIT} в день). Возвращайся завтра или оформи Pro для безлимита."
)


async def _get_user(message: Message) -> dict:
    return await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


@dp.message(CommandStart())
async def on_start(message: Message):
    await _get_user(message)
    await message.answer(WELCOME)


@dp.message(F.text == "/summary")
async def on_summary(message: Message):
    user = await _get_user(message)
    digest = await db.get_digest(user["id"])
    lines = [
        "Сводка за сегодня:",
        f"✅ Задачи: {digest['tasks_today']}",
        f"📝 Заметки: {digest['notes_today']}",
        f"🤝 Встречи: {digest['meetings_today']}",
        f"💸 Траты: {digest['money_today']}",
        f"🍽 Приёмы пищи: {digest['food_today']}",
    ]
    await message.answer("\n".join(lines))


# Claude returns naive local datetimes ("2026-09-20T15:00:00"); users are assumed to be
# in Moscow time for now, so tag them with the correct UTC offset before they hit Postgres
# (which otherwise assumes UTC and shifts the wall-clock time when read back).
USER_TZ_OFFSET = "+03:00"


def _localize(naive_iso: str | None) -> str | None:
    if not naive_iso:
        return None
    if "+" in naive_iso or naive_iso.endswith("Z"):
        return naive_iso
    return naive_iso + USER_TZ_OFFSET


async def _store_entry(user_id: str, data: dict):
    entry_type = data.get("entry_type")
    if entry_type == "task":
        await db.add_task(
            user_id, data.get("title") or data.get("description"), _localize(data.get("starts_at"))
        )
    elif entry_type == "meeting":
        await db.add_meeting(
            user_id,
            data.get("title") or data.get("description"),
            data.get("with_who"),
            _localize(data.get("starts_at")),
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
        await db.add_ritual_log(user_id, data.get("title") or data.get("description"))
    else:
        await db.add_note(user_id, data.get("description") or "")


def _format_when(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    today = datetime.now().date()
    if dt.date() == today:
        return f"сегодня в {dt.strftime('%H:%M')}"
    if dt.date().toordinal() - today.toordinal() == 1:
        return f"завтра в {dt.strftime('%H:%M')}"
    return dt.strftime("%d.%m в %H:%M")


def _format_reply(data: dict) -> str:
    entry_type = data.get("entry_type")
    if entry_type == "task":
        when = _format_when(data.get("starts_at"))
        due = f" (до {when})" if when else ""
        reply = f"✅ Задача: {data.get('title') or data.get('description')}{due}"
    elif entry_type == "meeting":
        when = _format_when(data.get("starts_at"))
        when_str = f" {when}" if when else ""
        with_who = f" с {data['with_who']}" if data.get("with_who") else ""
        reply = f"🤝 Встреча{with_who}{when_str}"
    elif entry_type == "money":
        reply = f"💸 Записал: {data.get('amount')}₽ — {data.get('category') or data.get('description')}"
    elif entry_type == "food":
        reply = f"🍽 Записал: {data.get('description')} (~{data.get('calories')} ккал)"
    elif entry_type == "ritual":
        reply = f"🔁 Ритуал: {data.get('title') or data.get('description')}"
    else:
        reply = f"📝 Записал: {data.get('description')}"

    comment = data.get("comment")
    if comment:
        reply += f"\n\n{comment}"
    return reply


@dp.message(F.photo)
async def on_photo(message: Message):
    user = await _get_user(message)
    if not await db.check_and_increment_quota(user):
        await message.answer(QUOTA_EXCEEDED)
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buffer = await message.bot.download_file(file.file_path)
    image_bytes = buffer.read()

    try:
        data = ai.classify_photo(image_bytes, "image/jpeg", caption=message.caption)
    except Exception:
        logging.exception("classify_photo failed")
        await message.answer("Не смог распознать фото, попробуй ещё раз.")
        return

    await _store_entry(user["id"], data)
    await message.answer(_format_reply(data))


@dp.message(F.text)
async def on_text(message: Message):
    user = await _get_user(message)
    if not await db.check_and_increment_quota(user):
        await message.answer(QUOTA_EXCEEDED)
        return

    try:
        data = ai.classify_text(message.text)
    except Exception:
        logging.exception("classify_text failed")
        await message.answer("Не смог разобрать сообщение, попробуй переформулировать.")
        return

    await _store_entry(user["id"], data)
    await message.answer(_format_reply(data))


WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-secret")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"


async def _run_local_dev(bot: Bot):
    """Polling + a separate API port — simplest loop for local development."""
    import api
    from aiohttp import web

    app = api.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("API_PORT", 8081))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"API server listening on :{port}")

    await asyncio.gather(dp.start_polling(bot), asyncio.Event().wait())


async def _run_render(bot: Bot, external_url: str):
    """Single aiohttp app serving the Telegram webhook + the Mini App API —
    what Render's free web service (one process, one port) needs."""
    import api
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    app = api.create_app()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def _on_startup(_):
        await bot.set_webhook(f"{external_url}{WEBHOOK_PATH}")
        logging.info(f"Webhook set to {external_url}{WEBHOOK_PATH}")

    app.on_startup.append(_on_startup)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Serving webhook + API on :{port}")
    await asyncio.Event().wait()


async def main():
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        await _run_render(bot, external_url)
    else:
        await _run_local_dev(bot)


if __name__ == "__main__":
    asyncio.run(main())
