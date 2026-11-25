"""
Production AI Agent — Part 6 Final Project

Chạy:  uvicorn app.main:app --workers 2
Chấm:  python check_production_ready.py
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ──────────────────────────────────────
# Structured logging: mỗi dòng log là 1 JSON object
# ──────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "msg": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger("agent")


def log_event(event: str, **fields) -> None:
    logger.info(event, extra={"event": event, "fields": fields})


START_TIME = time.time()
_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """uvicorn bắt SIGTERM: ngừng nhận kết nối mới, chờ request đang chạy xong rồi chạy phần shutdown."""
    global _ready
    _ready = True
    log_event("startup", environment=settings.environment, port=settings.port)
    yield
    _ready = False
    log_event("shutdown", note="graceful shutdown complete")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log_event(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy, kể cả khi Redis chết (restart cũng không cứu được Redis)."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness: 503 khi Redis không kết nối được, để load balancer không gửi traffic vào."""
    if not _ready or not redis_healthy():
        return JSONResponse(status_code=503, content={"ready": False, "reason": "redis unavailable"})
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    # Mock LLM không trả số token thật nên ước lượng theo số từ.
    input_tokens = max(1, int(len(body.question.split()) * 1.3))
    output_tokens = max(1, int(len(answer.split()) * 1.3))
    cost = record_cost(input_tokens, output_tokens)
    log_event("agent_response", input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 8))

    return {"question": body.question, "answer": answer}
