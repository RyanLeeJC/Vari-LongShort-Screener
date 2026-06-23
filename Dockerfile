# Python from Docker Hub (same approach as GridBot) — avoids Render native Python source builds.
FROM node:22-bookworm-slim AS frontend

WORKDIR /app/longshort-screener
COPY longshort-screener/package.json longshort-screener/package-lock.json ./
RUN npm ci
COPY longshort-screener .
RUN npm run build

FROM python:3.12.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /app/longshort-screener/dist ./longshort-screener/dist

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
