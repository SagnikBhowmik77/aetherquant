# ── AetherQuant multi-stage build ─────────────────────────────
# Stage 1: build the React frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# Stage 2: Python API serving the built frontend (api_server.py mounts
# ./static when present, so one process serves both UI and /api)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY agent/requirements.txt .
RUN pip install -r requirements.txt
COPY agent/ .
COPY --from=web /web/dist ./static

EXPOSE 8700
# hosts like Render inject $PORT; default to 8700 for local `docker run`
CMD ["sh", "-c", "python -m uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8700}"]
