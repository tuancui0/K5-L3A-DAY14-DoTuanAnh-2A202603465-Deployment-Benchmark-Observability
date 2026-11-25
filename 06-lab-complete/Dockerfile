# ============================================================
# Production Dockerfile — multi-stage, slim, non-root, có HEALTHCHECK
# ============================================================

# Stage 1: builder — cài dependencies vào virtualenv
FROM python:3.11-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime — chỉ copy virtualenv và source
FROM python:3.11-slim AS runtime
RUN groupadd -r app && useradd -r -g app -d /app app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/
COPY utils/ ./utils/
RUN chown -R app:app /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.getenv('PORT','8000'), timeout=3)"

# `exec` để uvicorn là PID 1, nhận SIGTERM trực tiếp khi `docker stop`; lắng nghe theo $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
