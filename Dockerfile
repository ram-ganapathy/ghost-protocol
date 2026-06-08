# ── Stage 1: build React frontend ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install dependencies first (layer-cached unless package.json changes)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts

# Build
COPY frontend/ .
RUN npm run build

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

# Keeps Python from buffering stdout/stderr (cleaner logs in containers)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install Python dependencies before copying source (better layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ .

# Copy Vite build output into ./static/ so FastAPI can serve it
COPY --from=frontend-builder /build/dist ./static

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
