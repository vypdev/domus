# The Supervisor builds this folder. Fetch only the reviewed immutable runtime.
FROM ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv
FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS builder
COPY --from=uv /uv /usr/local/bin/uv
ARG DOMUS_SOURCE_COMMIT=98bd12f1bf141ba64053730b2686bd848aee1b1c
ARG DOMUS_SOURCE_SHA256=4531e8b013e288bcc717c72452c57018a1158f4aa6054f277b19b05d6baaa63f
ADD https://codeload.github.com/vypdev/domus/tar.gz/${DOMUS_SOURCE_COMMIT} /tmp/source.tar.gz
RUN printf '%s  /tmp/source.tar.gz\n' "$DOMUS_SOURCE_SHA256" | sha256sum --check - \
    && mkdir /app \
    && tar --extract --gzip --file=/tmp/source.tar.gz --directory=/app --strip-components=1
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
RUN uv sync --frozen --no-dev --package domus-server --no-editable

FROM python:3.14.6-slim-trixie@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144
ARG BUILD_VERSION=0.0.0-edge.1
ARG BUILD_ARCH
ARG DOMUS_SOURCE_COMMIT=98bd12f1bf141ba64053730b2686bd848aee1b1c
LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.source="https://github.com/vypdev/domus" \
      org.opencontainers.image.revision="${DOMUS_SOURCE_COMMIT}"
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)"
ENTRYPOINT ["/app/.venv/bin/domus-ingress", "--channel", "edge"]
