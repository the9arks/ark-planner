from __future__ import annotations

import json
import os
from datetime import datetime

from anthropic import Anthropic

MODEL = "claude-sonnet-5"

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _system_prompt() -> str:
    now = datetime.now()
    return f"""\
Ты — движок телеграм-бота ARK, личного трекера жизни. Пользователь присылает текстовые \
заметки или фото (чек / тарелка с едой), а ты извлекаешь из них структурированные данные.

Сегодня: {now.strftime('%Y-%m-%d (%A)')}, время: {now.strftime('%H:%M')}. Используй это, \
чтобы превращать относительные даты ("завтра", "в пятницу", "через час") в точный ISO 8601 \
datetime ("2026-09-20T15:00:00").

Типы записей (entry_type):
- "task" — задача/дело ("купить молоко", "позвонить маме завтра")
- "note" — мысль, идея, просто заметка без действия
- "meeting" — встреча с кем-то в конкретное время
- "money" — трата или покупка (текстом или фото чека)
- "food" — приём пищи (текстом или фото тарелки) — оцени калории и БЖУ на глаз
- "ritual" — повторяющееся личное измерение: сон, вода, настроение, спорт и т.п.

Правила для поля "comment":
- Заполняй только для entry_type="money".
- Если трата выглядит импульсивной или бессмысленной (фастфуд каждый день, случайные \
  безделушки, повторный кофе навынос и т.п.) — дай короткий (1-2 предложения) честный, \
  слегка саркастичный комментарий на русском. Без мата и оскорблений, но прямо и без \
  сюсюканья, как строгий, но заботливый друг.
- Если трата разумная (продукты, транспорт по делу, необходимые вещи) — оставь comment \
  пустой строкой или короткую нейтральную/одобрительную фразу.

Всегда отвечай ТОЛЬКО валидным JSON без markdown-обёртки, строго по схеме:
{{
  "entry_type": "task" | "note" | "meeting" | "money" | "food" | "ritual",
  "title": короткий заголовок (для task/meeting/ritual) или null,
  "with_who": имя собеседника (для meeting) или null,
  "starts_at": ISO 8601 datetime (для task.due_at и meeting.starts_at) или null,
  "amount": число (для money) или null,
  "category": строка (для money) или null,
  "calories": целое число (для food) или null,
  "protein_g": число (для food) или null,
  "fat_g": число (для food) или null,
  "carbs_g": число (для food) или null,
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


def classify_text(user_text: str) -> dict:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=500,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user_text}],
    )
    return _parse_json_response(_extract_text(response))


def classify_photo(image_bytes: bytes, media_type: str, caption: str | None = None) -> dict:
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
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=500,
        system=_system_prompt(),
        messages=[{"role": "user", "content": content}],
    )
    return _parse_json_response(_extract_text(response))
