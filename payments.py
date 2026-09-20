"""Platega.io payment integration. Docs: https://docs.platega.io

Needs PLATEGA_MERCHANT_ID + PLATEGA_SECRET_KEY env vars, issued by the Platega
manager once they've reviewed this purchase flow. Until those are set,
is_configured() is False and the bot shows a "coming soon" message instead of
a broken buy button.
"""

from __future__ import annotations

import os

import aiohttp

PLATEGA_BASE = "https://app.platega.io"

PRICING = {
    "pro": {"month": 199, "year": 1990, "lifetime": 4990},
    "ultra": {"month": 599, "year": 5990, "lifetime": 9990},
}
PERIOD_DAYS = {"month": 30, "year": 365, "lifetime": None}
PERIOD_LABEL = {"month": "1 месяц", "year": "1 год", "lifetime": "навсегда"}
TIER_LABEL = {"pro": "Pro", "ultra": "Ultra"}

BOT_USERNAME = os.environ.get("BOT_USERNAME", "ARKPlannerBot")


def is_configured() -> bool:
    return bool(os.environ.get("PLATEGA_MERCHANT_ID") and os.environ.get("PLATEGA_SECRET_KEY"))


async def create_payment(order_id: str, telegram_id: int, username: str | None, tier: str, period: str) -> dict:
    """Creates a Platega transaction and returns {transactionId, status, url, expiresIn, rate}."""
    amount = PRICING[tier][period]
    headers = {
        "X-MerchantId": os.environ["PLATEGA_MERCHANT_ID"],
        "X-Secret": os.environ["PLATEGA_SECRET_KEY"],
        "Content-Type": "application/json",
    }
    body = {
        "paymentDetails": {"amount": amount, "currency": "RUB"},
        "description": f"ARK PLANNER — {TIER_LABEL[tier]} ({PERIOD_LABEL[period]})",
        "return": f"https://t.me/{BOT_USERNAME}?start=paid",
        "failedUrl": f"https://t.me/{BOT_USERNAME}?start=payfail",
        "payload": order_id,
        "metadata": {"userId": str(telegram_id), "userName": username or str(telegram_id)},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{PLATEGA_BASE}/v2/transaction/process", json=body, headers=headers
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Platega error {resp.status}: {data}")
            return data


def verify_webhook_auth(merchant_id: str | None, secret: str | None) -> bool:
    return bool(
        merchant_id
        and secret
        and merchant_id == os.environ.get("PLATEGA_MERCHANT_ID")
        and secret == os.environ.get("PLATEGA_SECRET_KEY")
    )
