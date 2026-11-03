# Immutable published schema9 compatible administration checkpoint; never a Supervisor release folder.
FROM ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv
FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS source
ARG DOMUS_SOURCE_COMMIT=87d726fa5a6a8cbcb56e0b911d15cc5b8a96a470
ARG DOMUS_SOURCE_SHA256=d8a9c4c1caf3acbb462ac21ec78ccbab05d756031880fd2f5013b4e528b45758
ADD https://codeload.github.com/vypdev/domus/tar.gz/${DOMUS_SOURCE_COMMIT} /tmp/source.tar.gz
RUN printf '%s  /tmp/source.tar.gz\n' "$DOMUS_SOURCE_SHA256" | sha256sum --check - \
    && mkdir /app \
    && tar --extract --gzip --file=/tmp/source.tar.gz --directory=/app --strip-components=1
WORKDIR /app

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend
RUN npm install --global --ignore-scripts --no-audit --no-fund pnpm@10.34.0
WORKDIR /app
COPY --from=source /app/package.json /app/pnpm-lock.yaml /app/pnpm-workspace.yaml ./
COPY --from=source /app/frontend ./frontend
COPY --from=source /app/tests/fixtures/frontend-toolchain/package.json ./tests/fixtures/frontend-toolchain/package.json
RUN pnpm install --frozen-lockfile --filter @domus/frontend... \
    && pnpm build:frontend

FROM source AS builder
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=frontend /app/backend/src/domus/ui /app/backend/src/domus/ui
ENV UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
RUN uv sync --frozen --no-dev --package domus-server --no-editable
RUN .venv/bin/python -c "from pathlib import Path; import domus; from domus.entrypoints.ui_bundle import load_bundle; from domus.infrastructure.sqlite import SCHEMA_VERSION; assert SCHEMA_VERSION == 9; assert load_bundle(Path(domus.__file__).parent / 'ui') is not None"

FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144
ARG BUILD_VERSION=ci-schema9
ARG BUILD_ARCH
ARG DOMUS_SOURCE_COMMIT=87d726fa5a6a8cbcb56e0b911d15cc5b8a96a470
LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/vypdev/domus" \
      org.opencontainers.image.revision="${DOMUS_SOURCE_COMMIT}"
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 0:0
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)"
ENTRYPOINT ["/app/.venv/bin/domus-ha-app", "--channel", "edge"]
