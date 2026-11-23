# Imagen única para Google Cloud Run: compila el frontend y lo sirve desde FastAPI en el mismo puerto.
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/static \
    DATABASE_URL=sqlite:////tmp/ideator.db \
    VERTEX_CREDENTIALS_FILE=/nonexistent.json
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist ./static
RUN useradd --create-home ideator
USER ideator
# Una sola instancia y un solo proceso: la base SQLite se respalda en Cloud Storage (app/cloud.py).
CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips "*"
