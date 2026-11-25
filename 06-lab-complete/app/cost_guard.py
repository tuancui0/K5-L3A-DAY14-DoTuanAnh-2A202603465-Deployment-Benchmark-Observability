"""
Cost guard (tiêu chí 8).

Cộng dồn chi phí LLM (theo token) vào Redis theo ngày; vượt DAILY_BUDGET_USD → 402.
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _key() -> str:
    return "cost:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → 402."""
    try:
        spent = float(r.get(_key()) or 0.0)
    except Exception as exc:
        logger.warning("cost guard unavailable (redis error): %s", exc)
        return
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "spent_usd": round(spent, 6),
                "budget_usd": settings.daily_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(_key(), cost)
        pipe.expire(_key(), 3 * 24 * 3600)
        pipe.execute()
    except Exception as exc:
        logger.warning("cost guard could not record cost (redis error): %s", exc)
    return cost
