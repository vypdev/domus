"""App manifest and build contract prevent new exposure or mutable runtime sources."""

import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_repository_and_edge_manifest_offer_native_ha_entry_without_user_credentials() -> None:
    repository = yaml.safe_load((ROOT / "repository.yaml").read_text())
    manifest = yaml.safe_load((ROOT / "addon-edge/config.yaml").read_text())
    assert repository["url"] == "https://github.com/vypdev/domus"
    assert manifest["slug"] == "domus_edge" and manifest["stage"] == "experimental"
    assert manifest["boot"] == "manual" and manifest["version"] == "0.0.0-edge.5"
    assert manifest["ingress"] is True and manifest["ingress_port"] == 8099
    assert manifest["panel_admin"] is False and manifest["homeassistant_api"] is True
    assert manifest["options"] == {"public_origins": []}
    assert manifest["schema"] == {"public_origins": ["url"]}
    assert manifest["breaking_versions"] == ["0.0.0-edge.2", "0.0.0-edge.3", "0.0.0-edge.4"]
    assert set(manifest["arch"]) == {"amd64", "aarch64"}


def test_manifest_has_no_published_port_or_unneeded_host_privileges() -> None:
    manifest = yaml.safe_load((ROOT / "addon-edge/config.yaml").read_text())
    assert manifest["ports"] == {}
    for key in ("hassio_api", "auth_api", "host_network", "host_pid", "host_dbus", "full_access"):
        assert not manifest.get(key, False), key
    for key in ("privileged", "devices", "map", "docker_api", "image"):
        assert key not in manifest, key
    assert manifest["init"] is True and manifest["timeout"] >= 20


def test_build_pins_source_checksum_bases_lock_and_nonroot_native_entrypoint() -> None:
    source = (ROOT / "addon-edge/Dockerfile").read_text()
    bases = re.findall(r"^FROM (\S+)", source, re.MULTILINE)
    assert len(bases) == 5 and bases[3] == "source"
    assert all(re.search(r"@sha256:[a-f0-9]{64}$", b) for b in bases if b != "source")
    assert " AS source" in source.split("FROM source AS builder")[0]
    assert (
        "node:24.20.0-bookworm-slim@sha256:"
        "ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend"
    ) in source
    commits = re.findall(r"^ARG DOMUS_SOURCE_COMMIT=(\w+)$", source, re.MULTILINE)
    assert len(commits) == 2 and len(set(commits)) == 1
    assert re.fullmatch(r"[a-f0-9]{40}", commits[0])
    assert commits[0] == "271a3a07feb1535f0a5ec8b55abb3de9aac049a9"
    assert (
        "DOMUS_SOURCE_SHA256=5cc9a963b6f064aa48be256a9d5a4274f8c52c878e4ad7f84517cd33f41056c8"
        in source
    )
    assert "ARG BUILD_VERSION=0.0.0-edge.5" in source
    assert re.search(r"^ARG DOMUS_SOURCE_SHA256=[a-f0-9]{64}$", source, re.MULTILINE)
    assert "sha256sum --check" in source
    assert "https://codeload.github.com/vypdev/domus/tar.gz/${DOMUS_SOURCE_COMMIT}" in source
    assert "uv sync --frozen --no-dev --package domus-server --no-editable" in source
    assert "USER 0:0" in source and "UV_PYTHON_DOWNLOADS=never" in source
    assert 'ENTRYPOINT ["/app/.venv/bin/domus-ha-app", "--channel", "edge"]' in source
    assert "EXPOSE" not in source and "SUPERVISOR_TOKEN" not in source
    assert "pnpm@10.34.0" in source and "pnpm install --frozen-lockfile" in source
    assert "pnpm build:frontend" in source
    assert source.index(
        "COPY --from=frontend /app/backend/src/domus/ui /app/backend/src/domus/ui"
    ) < source.index("RUN uv sync")
    final = source.rsplit("FROM ", 1)[1]
    assert "node" not in final and "pnpm" not in final and "npm" not in final
    assert "COPY --from=builder /app/.venv /app/.venv" in final


def test_legacy_builder_preserves_the_actual_published_edge_three_recipe() -> None:
    data = (ROOT / "tests/fixtures/edge3-app/Dockerfile").read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "0b7c878e9af9bfa36e72fd9de3fe97c115e088cbe55a9680106701352d4afac8"
    )
    assert b"ARG BUILD_VERSION=0.0.0-edge.3" in data
    assert b"ARG DOMUS_SOURCE_COMMIT=faa1654a5c9cddb562bfcd4c02d4cebfeb78e9f5" in data


def test_native_options_explain_the_one_time_origin_configuration_without_a_new_login() -> None:
    text = yaml.safe_load((ROOT / "addon-edge/translations/en.yaml").read_text())
    field = text["configuration"]["public_origins"]
    assert field["name"] == "Home Assistant browser origins"
    assert "one to four" in field["description"] and "existing HA sign-in" in field["description"]
