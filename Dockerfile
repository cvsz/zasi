FROM node:22.14.0-bookworm-slim AS cockpit-build

WORKDIR /frontend
COPY package.json package-lock.json vite.config.js ./
COPY web ./web
RUN npm ci --ignore-scripts \
    && npm run build

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md /app/
COPY main.py /app/main.py
COPY backend /app/backend
COPY src /app/src
COPY scripts /app/scripts
COPY --from=cockpit-build /frontend/web/dist /app/web/dist

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin zasi \
    && pip install --no-cache-dir . \
    && install -d -m 700 /app/data \
    && chown -R 10001:10001 /app

EXPOSE 8080

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3)"]

CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
