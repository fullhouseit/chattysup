# --- Stage 1: build the SPA -------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts writes to `../backend/app/static`, i.e. /backend/app/static.
RUN npm run build

# --- Stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /backend/app/static ./app/static

# Attachments and — when no external database is configured — the SQLite file
# both live on the /data volume so they survive a container rebuild.
ENV STORAGE_PATH=/data/storage \
    DATABASE_URL=sqlite+aiosqlite:////data/chattysup.db
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
