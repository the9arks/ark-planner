from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from anthropic import Anthropic, APIError

MODEL = "claude-sonnet-5"

_client: Anthropic | None = None


class ServiceUnavailable(Exception):
    """The Claude API call itself failed (rate limit, auth/billing hold,
    connectivity) — distinct from a JSON-parsing failure, so callers can show
    an honest "we're down" message instead of blaming the user's phrasing."""


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _system_prompt(tz_offset: int = 3) -> str:
    now = datetime.now(timezone(timedelta(hours=tz_offset)))
    return f"""\
Ты — движок телеграм-бота ARK, личного трекера жизни. Пользователь присылает текстовые \
заметки или фото (чек / тарелка с едой), а ты извлекаешь из них структурированные данные.

Сегодня у пользователя: {now.strftime('%Y-%m-%d (%A)')}, время: {now.strftime('%H:%M')} \
(часовой пояс пользователя, UTC{'+' if tz_offset >= 0 else ''}{tz_offset}). Используй это, \
чтобы превращать относительные даты ("завтра", "в пятницу", "через час") в точный ISO 8601 \
datetime без указания зоны, в местном времени пользователя ("2026-09-20T15:00:00").

Разговорное время суток (обязательно учитывай при разборе часов без AM/PM):
- "утра" → 5-11 часов ("7 утра" = 07:00)
- "дня" → 12-17 часов ("2 дня" = 14:00, "12 дня" = 12:00)
- "вечера" → 18-23 часа ("6 вечера" = 18:00, "10 вечера" = 22:00)
- "ночи" → 0-4 часа ("2 ночи" = 02:00)
- Без уточнения и число ≤ 7 — считай вечером/днём по здравому смыслу (например просто "в 6" \
  без контекста, скорее всего, 18:00, не 06:00).

Типы записей (entry_type):
- "task" — задача/дело, в том числе разовое событие с напоминанием ("купить молоко", \
  "завтра в 18:00 тренировка, напомни")
- "note" — мысль, идея, просто заметка без действия
- "meeting" — встреча с кем-то в конкретное время
- "money" — трата или покупка (текстом или фото чека)
- "food" — приём пищи (текстом или фото тарелки) — оцени калории и БЖУ на глаз
- "ritual" — ПОВТОРЯЮЩАЯСЯ привычка по дням недели, или разовое измерение (сон, вода, настроение)

Разовое напоминание (например "завтра в 18:00 тренировка, напомни" или "напомни в 15:00 позвонить \
маме"):
- Это entry_type="task". Заполни starts_at точным временем, remind=true.
- ВАЖНО: относительные слова "завтра"/"сегодня"/"послезавтра" — это ОДИН конкретный день, \
  НЕ повторяющееся расписание по дням недели. Такое всегда task с starts_at, а не ritual.

Привычка с расписанием (например "тренировка бокс пн ср пт в 18:00, напомни за час") — только \
когда пользователь явно называет дни недели по имени ("понедельник", "пн", "по средам" и т.п.):
- Это entry_type="ritual", habit_action="define", дополнительно заполни days_of_week (массив: \
  "mon","tue","wed","thu","fri","sat","sun"), start_time ("18:00") и reminder_lead_minutes \
  (минут до начала — "за час"=60, "за полчаса"=30, "за полтора часа"=90, "за 15 минут"=15).

Привычка без расписания — человек заявляет цель бросить/начать что-то ("хочу бросить курить", \
"начинаю бегать по утрам", "месяц без алкоголя"):
- entry_type="ritual", habit_action="define", days_of_week/start_time оставь null.
- habit_type="quit" если человек хочет ОТ ЧЕГО-ТО ОТКАЗАТЬСЯ (курение, алкоголь, соцсети, \
  сахар, мастурбация и т.п. — если смысл в "бросить"/"не делать" — это quit). \
  habit_type="build" если хочет ЧТО-ТО НАЧАТЬ ДЕЛАТЬ регулярно (спорт, чтение, медитация).

Чек-ин по существующей привычке — человек сообщает, что сегодня держится/сделал \
("не курил сегодня", "сходил на тренировку", "держусь"):
- entry_type="ritual", habit_action="checkin", title — как можно ближе к названию привычки.

Срыв по привычке-отказу — человек признаётся, что сорвался ("сорвался", "не удержался, \
покурил", "выпил хотя бросаю"):
- entry_type="ritual", habit_action="relapse", title — название привычки.
- В comment ОБЯЗАТЕЛЬНО дай тёплую поддержку без осуждения (1 предложение) — никогда не \
  стыди, срыв это нормально, важно что человек не сдаётся.

Разовое измерение без привычки и расписания ("спал 6.5 часов", "выпил воды"):
- entry_type="ritual", habit_action оставь null, days_of_week/start_time оставь null.

Правила для поля "comment":
- Для entry_type="money": если трата выглядит импульсивной или бессмысленной (фастфуд каждый \
  день, случайные безделушки, повторный кофе навынос и т.п.) — дай короткий (1-2 предложения) \
  честный, слегка саркастичный комментарий на русском. Без мата и оскорблений, но прямо и без \
  сюсюканья, как строгий, но заботливый друг. Если трата разумная — оставь пустым или короткую \
  нейтральную фразу.
- Для entry_type="ritual" с habit_action="checkin" или "relapse": короткая (1 предложение) \
  тёплая поддержка на русском — для checkin можно с лёгкой похвалой, для relapse — обязательно \
  без осуждения, ободряюще.
- Для остальных типов — оставь пустым.

Всегда отвечай ТОЛЬКО валидным JSON без markdown-обёртки, строго по схеме:
{{
  "entry_type": "task" | "note" | "meeting" | "money" | "food" | "ritual",
  "title": короткий заголовок (для task/meeting/ritual) или null,
  "with_who": имя собеседника (для meeting) или null,
  "starts_at": ISO 8601 datetime (для task.due_at и meeting.starts_at) или null,
  "remind": true/false (для task — прислать напоминание в момент starts_at) или null,
  "amount": число (для money) или null,
  "category": строка (для money) или null,
  "calories": целое число (для food) или null,
  "protein_g": число (для food) или null,
  "fat_g": число (для food) или null,
  "carbs_g": число (для food) или null,
  "days_of_week": массив дней недели (для ritual-привычки с расписанием) или null,
  "start_time": "HH:MM" (для ritual-привычки с расписанием) или null,
  "reminder_lead_minutes": целое число (для ritual-привычки с расписанием) или null,
  "habit_action": "define" | "checkin" | "relapse" (для entry_type=ritual, если применимо) или null,
  "habit_type": "build" | "quit" (для habit_action=define) или null,
  "description": короткое описание на русском,
  "comment": строка (может быть пустой)
}}
"""


def _extract_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError("No text block in Claude response")


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def classify_text(user_text: str, tz_offset: int = 3) -> dict:
    try:
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=800,
            system=_system_prompt(tz_offset),
            messages=[{"role": "user", "content": user_text}],
        )
    except APIError as e:
        raise ServiceUnavailable(str(e)) from e
    return _parse_json_response(_extract_text(response))


def classify_photo(
    image_bytes: bytes, media_type: str, caption: str | None = None, tz_offset: int = 3
) -> dict:
    import base64

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64_image},
        },
        {
            "type": "text",
            "text": (
                "Определи, это фото чека (entry_type=money) или фото еды (entry_type=food), "
                "и извлеки данные по схеме. Если чек — сложи все позиции в amount и опиши "
                "категорию покупки. Если еда — оцени калорийность и БЖУ порции на глаз."
                + (f"\nПодпись от пользователя: {caption}" if caption else "")
            ),
        },
    ]
    try:
        response = get_client().messages.create(
            model=MODEL,
            max_tokens=800,
            system=_system_prompt(tz_offset),
            messages=[{"role": "user", "content": content}],
        )
    except APIError as e:
        raise ServiceUnavailable(str(e)) from e
    return _parse_json_response(_extract_text(response))
