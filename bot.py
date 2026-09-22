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
import payments

load_dotenv()

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

INTRO_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "assets", "ark-intro.mp4")

MINIAPP_URL = os.environ.get("MINIAPP_URL", "https://ark-planner-miniapp.onrender.com")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "ARKPlannerBot")
QUICK_CAPTURE_BASE = os.environ.get("QUICK_CAPTURE_BASE", "https://ark-planner-backend.onrender.com")
SUPPORT_URL = "https://t.me/ark_planner_support"
ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "0") or "0")
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

🎁 Приглашай друзей — вы оба получите по 3 дня Pro бесплатно (кнопка ниже).
""".format(free=db.TIER_DAILY_LIMITS["free"], pro=db.TIER_DAILY_LIMITS["pro"])

TARIFFS_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "tariffs.jpg")

QUOTA_EXCEEDED_CAPTION = """\
😮 На сегодня бесплатные запросы закончились ({limit} из {limit})

Похоже, ARK реально тебе полезен — это хороший знак. Чтобы не ждать до завтра:

<b>Pro</b> — {pro} запросов в день, 199₽/мес
<b>Ultra</b> — без ограничений вообще, 599₽/мес

Или пригласи друга — вы оба получите по 3 дня Pro (кнопка «Пригласить» на /start).""".format(
    limit=db.FREE_DAILY_AI_LIMIT, pro=db.TIER_DAILY_LIMITS["pro"]
)

PROFILE_INFO_TEXT = """\
🔒 ARK хранит то, что ты присылаешь: сообщения, фото, и записи, которые из них получаются \
(задачи, встречи, траты, еда, привычки).

Зачем: чтобы распознавать текст/фото и присылать тебе сводки и напоминания.

Третьим лицам не передаём — кроме технических партнёров (Claude — распознавание, Supabase — \
хранение, Platega — платежи).

Полный текст — /privacy, условия использования — /terms. Выгрузить или стереть всё — в любой момент через /support."""

TARIFFS_TEXT = """\
💳 <b>Тарифы ARK PLANNER</b>

<b>Free</b> — {free} AI-действий в день, 0₽
<b>Pro</b> — {pro} AI-действий в день, <s>399₽</s> <b>199₽/мес</b> (<s>3990₽</s> <b>1990₽/год</b>, <s>9990₽</s> <b>4990₽ навсегда</b>)
<b>Ultra</b> — безлимит, <s>1199₽</s> <b>599₽/мес</b> (<s>11990₽</s> <b>5990₽/год</b>, <s>19990₽</s> <b>9990₽ навсегда</b>)

🔥 Скидка -50% — выбери тариф кнопкой ниже.""".format(
    free=db.TIER_DAILY_LIMITS["free"], pro=db.TIER_DAILY_LIMITS["pro"]
)

def _quick_capture_url(secret: str) -> str:
    return f"{QUICK_CAPTURE_BASE}/shortcut/{secret}/entry"


def _shortcut_setup_steps(url: str) -> str:
    return (
        "1. Открой приложение «Команды» → «+» → «Добавить действие»\n"
        "2. Найди и добавь «Надиктовать текст» (Dictate Text)\n"
        "3. Добавь действие «Получить содержимое URL» (Get Contents of URL):\n"
        f"   • URL: <code>{url}</code>\n"
        "   • Метод: POST\n"
        "   • Тело запроса: JSON → поле <code>text</code> = переменная «Надиктованный текст»\n"
        "4. Сохрани команду, назови, например, «ARK»"
    )


async def _quick_capture_link(tg_user) -> str:
    user = await _get_user_from(tg_user)
    secret = user.get("quick_secret") or await db.get_or_create_quick_secret(user["id"])
    return _quick_capture_url(secret)


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
                InlineKeyboardButton(text="🎁 Пригласить", callback_data="info_referral"),
            ],
            [InlineKeyboardButton(text="🛟 Поддержка", url=SUPPORT_URL)],
        ]
    )


async def _get_user(message: Message) -> dict:
    return await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


async def _get_user_from(tg_user) -> dict:
    return await db.get_or_create_user(
        telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name
    )


SUBSCRIBE_TEXT = (
    "Чтобы пользоваться ARK PLANNER, подпишись на наш канал 👇\n\n"
    "Там фичи, новости и бонусы для подписчиков."
)


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=core.REQUIRED_CHANNEL_URL)],
            [InlineKeyboardButton(text="✅ Я подписался, проверить", callback_data="check_subscription")],
        ]
    )


async def _require_subscription(message: Message, telegram_id: int) -> bool:
    if await core.is_subscribed(telegram_id):
        return True
    await message.answer(SUBSCRIBE_TEXT, reply_markup=_subscribe_keyboard())
    return False


@dp.callback_query(F.data == "check_subscription")
async def on_check_subscription(callback: CallbackQuery):
    core.clear_subscription_cache(callback.from_user.id)
    if await core.is_subscribed(callback.from_user.id):
        await callback.message.answer(
            "✅ Подписка подтверждена! Теперь можно пользоваться ARK PLANNER — просто напиши, что нужно записать."
        )
        await callback.answer()
    else:
        await callback.answer("Не вижу подписки — попробуй ещё раз через пару секунд.", show_alert=True)


@dp.message(CommandStart())
async def on_start(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None

    referrer_tg_id = None
    if payload and payload.startswith("ref") and payload[3:].isdigit():
        candidate = int(payload[3:])
        if candidate != message.from_user.id:
            referrer_tg_id = candidate

    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        referrer_telegram_id=referrer_tg_id,
    )

    if user.get("_is_new") and referrer_tg_id:
        await message.answer(
            "🎁 Ты пришёл по приглашению — начислил тебе 3 дня Pro бесплатно!\n"
            "Другу тоже начислено 3 дня Pro в благодарность 🙌"
        )

    if payload == "buy":
        await _send_tariffs(message, TARIFFS_TEXT)
        return
    if payload == "paid":
        await message.answer("Спасибо! Если оплата прошла успешно — тариф обновится в течение минуты.")
        return
    if payload == "payfail":
        await message.answer("Оплата не прошла. Можно попробовать ещё раз через «Тарифы».")
        return

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


@dp.callback_query(F.data == "info_referral")
async def on_info_referral(callback: CallbackQuery):
    user = await _get_user_from(callback.from_user)
    count = await db.count_referrals(user["id"])
    link = f"https://t.me/{BOT_USERNAME}?start=ref{user['telegram_id']}"
    text = (
        "🎁 <b>Приглашай друзей — получай Pro бесплатно</b>\n\n"
        f"Твоя ссылка:\n{link}\n\n"
        "• Другу — 3 дня Pro бесплатно при первом запуске\n"
        "• Тебе — 3 дня Pro за каждого друга\n\n"
        f"Уже пригласил: {count}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Поделиться ссылкой",
                    url=f"https://t.me/share/url?url={link}&text=Веду задачи, траты и еду через ARK PLANNER — попробуй",
                )
            ]
        ]
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "info_profile")
async def on_info_profile(callback: CallbackQuery):
    await callback.message.answer(PROFILE_INFO_TEXT)
    await callback.answer()


def _tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Pro — 199₽/мес (-50%)", callback_data="buy_pro_month"),
                InlineKeyboardButton(text="Ultra — 599₽/мес (-50%)", callback_data="buy_ultra_month"),
            ],
            [
                InlineKeyboardButton(text="Pro — 1990₽/год (-50%)", callback_data="buy_pro_year"),
                InlineKeyboardButton(text="Ultra — 5990₽/год (-50%)", callback_data="buy_ultra_year"),
            ],
            [
                InlineKeyboardButton(text="Pro — 4990₽ навсегда (-50%)", callback_data="buy_pro_lifetime"),
                InlineKeyboardButton(text="Ultra — 9990₽ навсегда (-50%)", callback_data="buy_ultra_lifetime"),
            ],
            [InlineKeyboardButton(text="🎁 Пригласить друга вместо оплаты", callback_data="info_referral")],
        ]
    )


async def _send_tariffs(message: Message, caption: str):
    keyboard = _tariffs_keyboard()
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


@dp.callback_query(F.data.startswith("buy_"))
async def on_buy(callback: CallbackQuery):
    _, tier, period = callback.data.split("_")
    if tier not in payments.PRICING or period not in payments.PERIOD_DAYS:
        await callback.answer()
        return

    if not payments.is_configured():
        await callback.message.answer(
            "Оплата подключается, совсем скоро будет доступна 🙌 Загляни чуть позже — "
            "или пригласи друга и получи Pro бесплатно (кнопка «Пригласить» на /start)."
        )
        await callback.answer()
        return

    user = await _get_user_from(callback.from_user)
    amount = payments.PRICING[tier][period]
    order = await db.create_order(user["id"], tier, period, amount)

    try:
        result = await payments.create_payment(
            order["id"], user["telegram_id"], user.get("username"), tier, period
        )
    except Exception:
        logging.exception("create_payment failed")
        await callback.message.answer("Не получилось создать оплату, попробуй ещё раз чуть позже.")
        await callback.answer()
        return

    await db.set_order_transaction(order["id"], result["transactionId"])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=result["url"])]]
    )
    await callback.message.answer(
        f"💳 {payments.TIER_LABEL[tier]} — {payments.PERIOD_LABEL[period]}, {amount}₽\n"
        "Ссылка активна 15 минут. После оплаты тариф включится автоматически.",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(F.data == "info_action_button")
async def on_info_action_button(callback: CallbackQuery):
    url = await _quick_capture_link(callback.from_user)
    text = (
        "⚡️ <b>Кнопка действия (iPhone 15 Pro и новее)</b>\n\n"
        "Настрой один раз — дальше просто: зажал боковую кнопку → сказал → готово, "
        "без открытия чатов и приложений.\n\n"
        f"{_shortcut_setup_steps(url)}\n"
        "5. Настройки → Кнопка действия → выбери команду «ARK»\n\n"
        "Ссылка личная — не передавай её другим."
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "info_double_tap")
async def on_info_double_tap(callback: CallbackQuery):
    url = await _quick_capture_link(callback.from_user)
    text = (
        "👆 <b>Двойной тап по задней крышке</b>\n\n"
        f"{_shortcut_setup_steps(url)}\n"
        "5. Настройки → Специальные возможности → Касание → Нажатие задней панели → "
        "Двойное нажатие → выбери команду «ARK»\n\n"
        "Ссылка личная — не передавай её другим."
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@dp.message(Command("privacy"))
async def on_privacy(message: Message):
    await message.answer(f"{PROFILE_INFO_TEXT}\n\nПолный текст: {PRIVACY_URL}")


@dp.message(Command("terms"))
async def on_terms(message: Message):
    await message.answer(f"📄 Пользовательское соглашение ARK PLANNER:\n{TERMS_URL}")


@dp.message(Command("support"))
async def on_support(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Написать в поддержку", url=SUPPORT_URL)]]
    )
    await message.answer(
        "Если что-то не работает, есть вопрос по подписке или хочешь удалить данные — пиши:",
        reply_markup=keyboard,
    )


PROMO_CODE_RE = re.compile(r"^[A-Z0-9]{4,6}$")


@dp.message(Command("addpromo"))
async def on_add_promo(message: Message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Формат: <code>/addpromo КОД Имя партнёра [ставка%]</code>\n"
            "Код — 4-6 символов, английские буквы и цифры.\n"
            "Пример: <code>/addpromo VIKA35 Виктория 35</code>",
            parse_mode="HTML",
        )
        return

    tokens = parts[1].split()
    code = tokens[0].upper()
    rest = tokens[1:]

    commission = 35.0
    if rest and re.fullmatch(r"\d+(\.\d+)?", rest[-1]):
        commission = float(rest[-1])
        rest = rest[:-1]

    partner_name = " ".join(rest).strip()
    if not PROMO_CODE_RE.match(code):
        await message.answer("Код должен быть 4-6 символов, только английские буквы и цифры.")
        return
    if not partner_name:
        await message.answer("Укажи имя партнёра: <code>/addpromo КОД Имя партнёра</code>", parse_mode="HTML")
        return

    try:
        await db.create_promo_code(code, partner_name, commission)
    except Exception:
        await message.answer(f"Не получилось создать — возможно, код «{code}» уже занят.")
        return

    await message.answer(
        f"✅ Промокод <code>{code}</code> → {partner_name} (ставка {commission:g}%)\n\n"
        "Бонус покупателю: месяц +5 дней, год +1 месяц, навсегда -10% к цене.\n"
        "Один человек может применить код только один раз.\n\n"
        "Статистика: /promostats",
        parse_mode="HTML",
    )


@dp.message(Command("promostats"))
async def on_promo_stats(message: Message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    codes = await db.get_promo_stats()
    if not codes:
        await message.answer("Промокодов пока нет — добавь через /addpromo.")
        return

    lines = ["💼 <b>Статистика по промокодам</b>\n"]
    total_payout = 0.0
    for c in codes:
        status = "" if c["active"] else " (выключен)"
        lines.append(
            f"<code>{c['code']}</code> — {c['partner_name']}{status}\n"
            f"  ставка {float(c['commission_percent']):g}% · {c['sales_count']} продаж · "
            f"выручка {c['revenue']:.0f}₽ · к выплате {c['payout']:.0f}₽"
        )
        total_payout += c["payout"]
    lines.append(f"\nИтого к выплате: <b>{total_payout:.0f}₽</b>")
    await message.answer("\n".join(lines), parse_mode="HTML")


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


@dp.message(F.voice | F.audio)
async def on_voice(message: Message):
    await message.answer(
        "🎤 Голосовые сообщения в чат пока не распознаю.\n\n"
        "Два рабочих способа надиктовать:\n"
        "• Микрофон на клавиатуре — надиктуй прямо в поле ввода, текст появится сам, останется отправить.\n"
        "• Кнопка действия / двойной тап по крышке — полностью автоматически, без открытия чата "
        "(инструкция на /start → «Кнопка действия»)."
    )


@dp.message(F.photo)
async def on_photo(message: Message):
    if not await _require_subscription(message, message.from_user.id):
        return
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
        entries = ai.classify_photo(
            image_bytes, "image/jpeg", caption=message.caption, tz_offset=tz_offset
        )
        entries = await core.store_entries(user["id"], entries, tz_offset)
        reply = core.format_replies(entries)
    except ai.ServiceUnavailable:
        logging.exception("on_photo: AI service unavailable")
        await db.refund_quota(user)
        await message.answer("⚠️ ARK временно недоступен (технические работы) — попробуй через несколько минут.")
        return
    except Exception:
        logging.exception("on_photo failed")
        await db.refund_quota(user)
        await message.answer("Не смог обработать фото, попробуй ещё раз.")
        return

    await message.answer(reply)


@dp.message(F.text)
async def on_text(message: Message):
    if not await _require_subscription(message, message.from_user.id):
        return
    user = await _get_user(message)
    if not await db.check_and_increment_quota(user):
        await _send_tariffs(message, QUOTA_EXCEEDED_CAPTION)
        return

    try:
        tz_offset = user.get("tz_offset", 3)
        entries = ai.classify_text(message.text, tz_offset=tz_offset)
        entries = await core.store_entries(user["id"], entries, tz_offset)
        reply = core.format_replies(entries)
    except ai.ServiceUnavailable:
        logging.exception("on_text: AI service unavailable")
        await db.refund_quota(user)
        await message.answer("⚠️ ARK временно недоступен (технические работы) — попробуй через несколько минут.")
        return
    except Exception:
        logging.exception("on_text failed")
        await db.refund_quota(user)
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


async def _reminder_loop():
    """Runs the digest/meal/meeting/habit/task reminder tick in-process every
    few minutes, so delivery doesn't depend on an external cron pinger hitting
    /cron/<secret> (Render's free tier has no native cron service)."""
    import reminders

    while True:
        try:
            await reminders.run_tick()
        except Exception:
            logging.exception("reminder tick failed")
        await asyncio.sleep(180)


async def _run_webhook(bot: Bot, external_url: str):
    """Single aiohttp app serving the Telegram webhook + the Mini App API —
    one process behind a reverse proxy (nginx on a VPS, or Render's single
    web service)."""
    import api
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    app = api.create_app()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def _on_startup(_):
        await bot.set_webhook(
            f"{external_url}{WEBHOOK_PATH}",
            allowed_updates=dp.resolve_used_update_types(),
        )
        logging.info(f"Webhook set to {external_url}{WEBHOOK_PATH}")
        asyncio.create_task(_reminder_loop())

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
            BotCommand(command="terms", description="Пользовательское соглашение"),
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
    # EXTERNAL_URL is what we set ourselves on a VPS; RENDER_EXTERNAL_URL is
    # auto-provided by Render — checking both means the same code deploys
    # to either without a flag day.
    external_url = os.environ.get("EXTERNAL_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        await _run_webhook(bot, external_url)
    else:
        await _run_local_dev(bot)


if __name__ == "__main__":
    asyncio.run(main())
