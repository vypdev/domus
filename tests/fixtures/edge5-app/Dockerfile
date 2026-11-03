# The Supervisor builds this folder. Fetch only the reviewed immutable runtime and UI.
FROM ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv
FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS source
ARG DOMUS_SOURCE_COMMIT=271a3a07feb1535f0a5ec8b55abb3de9aac049a9
ARG DOMUS_SOURCE_SHA256=5cc9a963b6f064aa48be256a9d5a4274f8c52c878e4ad7f84517cd33f41056c8
ADD https://codeload.github.com/vypdev/domus/tar.gz/${DOMUS_SOURCE_COMMIT} /tmp/source.tar.gz
RUN printf '%s  /tmp/source.tar.gz\n' "$DOMUS_SOURCE_SHA256" | sha256sum --check - \
    && mkdir /app \
    && tar --extract --gzip --file=/tmp/source.tar.gz --directory=/app --strip-components=1

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend
RUN npm install --global --ignore-scripts --no-audit --no-fund pnpm@10.34.0
COPY --from=source /app /app
WORKDIR /app
RUN pnpm install --frozen-lockfile --filter @domus/frontend... \
    && pnpm build:frontend

FROM source AS builder
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=frontend /app/backend/src/domus/ui /app/backend/src/domus/ui
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
RUN uv sync --frozen --no-dev --package domus-server --no-editable
RUN .venv/bin/python -c "from pathlib import Path; import domus; from domus.entrypoints.ui_bundle import load_bundle; assert load_bundle(Path(domus.__file__).parent / 'ui') is not None"

FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144
ARG BUILD_VERSION=0.0.0-edge.5
ARG BUILD_ARCH
ARG DOMUS_SOURCE_COMMIT=271a3a07feb1535f0a5ec8b55abb3de9aac049a9
LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/vypdev/domus" \
      org.opencontainers.image.revision="${DOMUS_SOURCE_COMMIT}"
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Only the fixed-path launcher provisions /data/domus as root; the server execs as 65532.
USER 0:0
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)"
ENTRYPOINT ["/app/.venv/bin/domus-ha-app", "--channel", "edge"]
