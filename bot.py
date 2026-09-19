from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from dotenv import load_dotenv

import ai
import core
import db

load_dotenv()

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

INTRO_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "assets", "ark-intro.mp4")

MINIAPP_URL = os.environ.get("MINIAPP_URL", "https://ark-planner-miniapp.onrender.com")
SUPPORT_URL = "https://t.me/ark_planner_support"
PRIVACY_URL = "https://telegra.ph/Politika-konfidencialnosti-ARK-PLANNER-09-19"
TERMS_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-ARK-PLANNER-09-19-2"

WELCOME = """\
🅰️ <b>ARK PLANNER</b> — твоя жизнь в одном сообщении

Надиктуй или напиши: «завтра в 3 встреча с Андреем, на обед борщ, не забыть оплатить интернет» \
→ встреча со временем, еда с калориями и задача сами появятся в нужных разделах.

Что умею:
• Голос или текст → задачи, встречи, деньги, еда, заметки, привычки
• Фото еды → точный подсчёт калорий и БЖУ
• Фото чека → трата занесена автоматически
• Утренний дайджест и напоминания — время под себя
• Привычки по дням недели с напоминанием заранее

<b>Free</b> — {free} AI-действий/день · <b>Pro</b> — 199₽/мес, {pro}/день · \
<b>Ultra</b> — 599₽/мес, безлимит
""".format(free=db.TIER_DAILY_LIMITS["free"], pro=db.TIER_DAILY_LIMITS["pro"])

TARIFFS_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "tariffs.jpg")

QUOTA_EXCEEDED_CAPTION = """\
😮 На сегодня бесплатные запросы закончились ({limit} из {limit})

Похоже, ARK реально тебе полезен — это хороший знак. Чтобы не ждать до завтра:

<b>Pro</b> — 20 запросов в день, 199₽/мес
<b>Ultra</b> — без ограничений вообще, 599₽/мес

Сменить тариф — «Настройки» в приложении, кнопка ниже.""".format(
    limit=db.FREE_DAILY_AI_LIMIT
)

PROFILE_INFO_TEXT = """\
🔒 ARK хранит то, что ты присылаешь: сообщения, фото, и записи, которые из них получаются \
(задачи, встречи, траты, еда, привычки).

Зачем: чтобы распознавать текст/фото и присылать тебе сводки и напоминания.

Третьим лицам не передаём — кроме технических партнёров (Claude — распознавание, Supabase — \
хранение, Platega — платежи).

Полный текст — /privacy. Выгрузить или стереть всё — в любой момент через /support."""

TARIFFS_TEXT = """\
💳 <b>Тарифы ARK PLANNER</b>

<b>Free</b> — {free} AI-действий в день, 0₽
<b>Pro</b> — {pro} AI-действий в день, 199₽/мес (1990₽/год, 4990₽ навсегда)
<b>Ultra</b> — безлимит, 599₽/мес (5990₽/год, 9990₽ навсегда)

Сменить тариф — раздел «Настройки» в приложении.""".format(
    free=db.TIER_DAILY_LIMITS["free"], pro=db.TIER_DAILY_LIMITS["pro"]
)

ACTION_BUTTON_TEXT = """\
⚡️ <b>Кнопка действия (iPhone 15 Pro и новее)</b>

Пока настраивается вручную через приложение «Команды»:
1. Команды → «+» → добавь действие «Диктовка текста»
2. Добавь действие «Открыть URL»: https://t.me/ARKPlannerBot?text=%TEXT%
3. Настройки → Кнопка действия → выбери свою команду

Полностью автоматическая настройка в одно нажатие — в разработке."""

DOUBLE_TAP_TEXT = """\
👆 <b>Двойной тап по задней крышке</b>

Настройки → Специальные возможности → Касание → Нажатие задней панели → Двойное нажатие → \
выбери ту же команду, что и для кнопки действия (см. /start → «Кнопка действия»).

Полностью автоматическая настройка — в разработке."""


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Как это работает", callback_data="info_profile")],
            [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=MINIAPP_URL))],
            [
                InlineKeyboardButton(text="⚡️ Кнопка действия", callback_data="info_action_button"),
                InlineKeyboardButton(text="👆 Двойной тап", callback_data="info_double_tap"),
            ],
            [
                InlineKeyboardButton(text="💳 Тарифы", callback_data="info_tariffs"),
                InlineKeyboardButton(text="🛟 Поддержка", url=SUPPORT_URL),
            ],
        ]
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
    keyboard = _main_keyboard()
    if os.path.exists(INTRO_VIDEO_PATH):
        await message.answer_animation(
            FSInputFile(INTRO_VIDEO_PATH),
            caption=WELCOME,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await message.answer(WELCOME, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "info_profile")
async def on_info_profile(callback: CallbackQuery):
    await callback.message.answer(PROFILE_INFO_TEXT)
    await callback.answer()


async def _send_tariffs(message: Message, caption: str):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть настройки", web_app=WebAppInfo(url=MINIAPP_URL))]
        ]
    )
    if os.path.exists(TARIFFS_IMAGE_PATH):
        await message.answer_photo(
            FSInputFile(TARIFFS_IMAGE_PATH), caption=caption, parse_mode="HTML", reply_markup=keyboard
        )
    else:
        await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "info_tariffs")
async def on_info_tariffs(callback: CallbackQuery):
    await _send_tariffs(callback.message, TARIFFS_TEXT)
    await callback.answer()


@dp.callback_query(F.data == "info_action_button")
async def on_info_action_button(callback: CallbackQuery):
    await callback.message.answer(ACTION_BUTTON_TEXT, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "info_double_tap")
async def on_info_double_tap(callback: CallbackQuery):
    await callback.message.answer(DOUBLE_TAP_TEXT, parse_mode="HTML")
    await callback.answer()


@dp.message(Command("privacy"))
async def on_privacy(message: Message):
    await message.answer(f"{PROFILE_INFO_TEXT}\n\nПолный текст: {PRIVACY_URL}")


@dp.message(Command("support"))
async def on_support(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url=SUPPORT_URL)]]
    )
    await message.answer(
        "Если что-то не работает, есть вопрос по подписке или хочешь удалить данные — пиши:",
        reply_markup=keyboard,
    )


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


TIME_COMMANDS = {
    "digest_time": ("morning_digest_time", "Утренний дайджест"),
    "breakfast_time": ("breakfast_reminder_time", "Напоминание про завтрак"),
    "lunch_time": ("lunch_reminder_time", "Напоминание про обед"),
    "dinner_time": ("dinner_reminder_time", "Напоминание про ужин"),
}


@dp.message(Command(*TIME_COMMANDS.keys()))
async def on_set_time(message: Message):
    command = message.text.split()[0].lstrip("/").split("@")[0]
    field, label = TIME_COMMANDS[command]
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2 or not re.fullmatch(r"[0-2]?\d:[0-5]\d", parts[1].strip()):
        await message.answer(f"Формат: /{command} ЧЧ:ММ, например /{command} 09:30")
        return

    time_str = parts[1].strip()
    hour, minute = map(int, time_str.split(":"))
    if hour > 23:
        await message.answer("Часы должны быть от 00 до 23.")
        return

    user = await _get_user(message)
    await db.set_user_time(user["id"], field, f"{hour:02d}:{minute:02d}")
    await message.answer(f"Готово: «{label}» теперь в {hour:02d}:{minute:02d}.")


@dp.message(F.photo)
async def on_photo(message: Message):
    user = await _get_user(message)
    if not await db.check_and_increment_quota(user):
        await _send_tariffs(message, QUOTA_EXCEEDED_CAPTION)
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buffer = await message.bot.download_file(file.file_path)
    image_bytes = buffer.read()

    try:
        tz_offset = user.get("tz_offset", 3)
        data = ai.classify_photo(
            image_bytes, "image/jpeg", caption=message.caption, tz_offset=tz_offset
        )
        await core.store_entry(user["id"], data, tz_offset)
        reply = core.format_reply(data)
    except Exception:
        logging.exception("on_photo failed")
        await message.answer("Не смог обработать фото, попробуй ещё раз.")
        return

    await message.answer(reply)


@dp.message(F.text)
async def on_text(message: Message):
    user = await _get_user(message)
    if not await db.check_and_increment_quota(user):
        await _send_tariffs(message, QUOTA_EXCEEDED_CAPTION)
        return

    try:
        tz_offset = user.get("tz_offset", 3)
        data = ai.classify_text(message.text, tz_offset=tz_offset)
        await core.store_entry(user["id"], data, tz_offset)
        reply = core.format_reply(data)
    except Exception:
        logging.exception("on_text failed")
        await message.answer("Не смог разобрать сообщение, попробуй переформулировать.")
        return

    await message.answer(reply)


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


async def _setup_bot_commands(bot: Bot):
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Что умеет ARK"),
            BotCommand(command="summary", description="Сводка за сегодня"),
            BotCommand(command="privacy", description="Приватность и данные"),
            BotCommand(command="support", description="Написать в поддержку"),
            BotCommand(command="digest_time", description="Время утреннего дайджеста, напр. 09:30"),
            BotCommand(command="breakfast_time", description="Время напоминания про завтрак"),
            BotCommand(command="lunch_time", description="Время напоминания про обед"),
            BotCommand(command="dinner_time", description="Время напоминания про ужин"),
        ]
    )


async def main():
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    await _setup_bot_commands(bot)
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        await _run_render(bot, external_url)
    else:
        await _run_local_dev(bot)


if __name__ == "__main__":
    asyncio.run(main())
