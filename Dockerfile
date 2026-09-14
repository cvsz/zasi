FROM node:22.14.0-bookworm-slim AS cockpit-build

WORKDIR /frontend
COPY package.json package-lock.json vite.config.js ./
COPY web ./web
RUN npm ci --ignore-scripts \
    && npm run build

FROM python:3.11-slim

ARG ZASI_BUILD_COMMIT

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ZASI_HOST=0.0.0.0 \
    ZASI_PORT=8080 \
    ZASI_ALLOW_PUBLIC_BIND=yes

COPY pyproject.toml README.md /app/
COPY main.py /app/main.py
COPY backend /app/backend
COPY src /app/src
COPY scripts /app/scripts
COPY --from=cockpit-build /frontend/web/dist /app/web/dist

RUN case "${ZASI_BUILD_COMMIT}" in \
      [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; \
      *) echo "ZASI_BUILD_COMMIT must be a lowercase 40-character git SHA" >&2; exit 2 ;; \
    esac \
    && printf '%s\n' "${ZASI_BUILD_COMMIT}" > /app/.zasi-release-commit \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin zasi \
    && python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir --no-build-isolation . \
    && python -m pip uninstall -y pip setuptools wheel jaraco.context backports.tarfile \
    && rm -rf /usr/local/lib/python3.11/ensurepip/_bundled \
    && install -d -m 700 /app/data \
    && chown -R 10001:10001 /app

EXPOSE 8080

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3)"]

CMD ["python3", "-m", "backend.runtime"]
