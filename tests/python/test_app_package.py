"""Guard immutable package inputs, build-only tools and unchanged HA privilege scope."""

import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_edge_package_advertises_the_explicit_schema_seven_upgrade_without_extra_privileges():
    manifest = yaml.load((ROOT / "addon-edge/config.yaml").read_text(), Loader=yaml.BaseLoader)
    assert manifest["version"] == "0.0.0-edge.4"
    assert manifest["breaking_versions"] == ["0.0.0-edge.2", "0.0.0-edge.3", "0.0.0-edge.4"]
    assert manifest["arch"] == ["amd64", "aarch64"]
    assert manifest["ingress"] == manifest["homeassistant_api"] == "true"
    assert manifest["hassio_api"] == manifest["auth_api"] == manifest["panel_admin"] == "false"
    assert manifest["ports"] == {}
    assert not set(manifest) & {"host_network", "privileged", "devices", "map", "full_access"}


def test_product_image_pins_the_verified_source_and_only_builds_ui_with_the_locked_node_image():
    source = (ROOT / "addon-edge/Dockerfile").read_text()
    assert source.count("ARG DOMUS_SOURCE_COMMIT=9f5cabe9cb4ffa5156f0fa01d8a3699a04f498af") == 2
    assert (
        "ARG DOMUS_SOURCE_SHA256=00290ba2611aa40183e4cb3e2c4cd36e5a60e483a6996a116e956386338d29b5"
        in source
    )
    assert (
        "node:24.20.0-bookworm-slim@sha256:"
        "ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend" in source
    )
    assert "pnpm@10.34.0" in source and "pnpm install --frozen-lockfile" in source
    assert "pnpm build:frontend" in source
    assert source.index(
        "COPY --from=frontend /app/backend/src/domus/ui /app/backend/src/domus/ui"
    ) < source.index("RUN uv sync")
    final = source.rsplit("FROM ", 1)[1]
    assert "node" not in final and "pnpm" not in final and "npm" not in final
    assert "COPY --from=builder /app/.venv /app/.venv" in final
    for line in source.splitlines():
        if line.startswith("FROM ") and ":" in line:
            assert re.search(r"@sha256:[a-f0-9]{64}(?: |$)", line)


def test_legacy_builder_preserves_the_actual_published_edge_three_recipe():
    data = (ROOT / "tests/fixtures/edge3-app/Dockerfile").read_bytes()
    assert (
        hashlib.sha256(data).hexdigest()
        == "0b7c878e9af9bfa36e72fd9de3fe97c115e088cbe55a9680106701352d4afac8"
    )
    assert b"ARG BUILD_VERSION=0.0.0-edge.3" in data
    assert b"ARG DOMUS_SOURCE_COMMIT=faa1654a5c9cddb562bfcd4c02d4cebfeb78e9f5" in data
