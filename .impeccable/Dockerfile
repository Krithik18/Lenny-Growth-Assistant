# Build frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# Backend runtime
FROM python:3.13-slim

WORKDIR /app

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

RUN pip install --no-cache-dir ./backend

WORKDIR /app/backend

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]