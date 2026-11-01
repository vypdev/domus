"""A bounded packaged build is snapshotted before serving; no request chooses a filesystem path."""

import json
from pathlib import Path

import pytest

from domus.domain.errors import StorageFailure
from domus.entrypoints.ui_bundle import load_bundle

HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Domus</title>'
    '<script id="domus-bootstrap" type="application/json">__DOMUS_BOOTSTRAP_V1__</script>'
    '<script type="module" crossorigin src="./assets/index-safe.js"></script>'
    '<link rel="stylesheet" crossorigin href="./assets/index-safe.css"></head>'
    '<body><div id="domus-entry"></div></body></html>'
)


def build(root: Path) -> Path:
    (root / "assets").mkdir(parents=True)
    (root / ".vite").mkdir()
    (root / "index.html").write_text(HTML)
    (root / "assets/index-safe.js").write_text("export const ready = true;")
    (root / "assets/index-safe.css").write_text("body { margin: 0; }")
    (root / ".vite/manifest.json").write_text(
        json.dumps(
            {
                "index.html": {
                    "file": "assets/index-safe.js",
                    "name": "index",
                    "src": "index.html",
                    "isEntry": True,
                    "css": ["assets/index-safe.css"],
                }
            }
        )
    )
    return root


def test_bundle_snapshots_declared_files_and_does_not_serve_manifest_or_later_changes(
    tmp_path: Path,
) -> None:
    root = build(tmp_path / "ui")
    bundle = load_bundle(root)
    assert bundle is not None
    assert bundle.template == HTML
    assert bundle.assets["assets/index-safe.js"] == (
        b"export const ready = true;",
        "text/javascript",
    )
    assert bundle.assets["assets/index-safe.css"][1] == "text/css"
    assert ".vite/manifest.json" not in bundle.assets
    (root / "assets/index-safe.js").write_text("changed")
    assert bundle.assets["assets/index-safe.js"][0] == b"export const ready = true;"
    with pytest.raises(TypeError):
        bundle.assets["new.js"] = (b"", "text/javascript")


def test_missing_optional_resource_is_distinct_from_a_corrupt_existing_bundle(
    tmp_path: Path,
) -> None:
    assert load_bundle(tmp_path / "absent") is None
    with pytest.raises(StorageFailure, match="ui_bundle_unavailable"):
        load_bundle(tmp_path)


def test_reachable_chunks_and_preloads_are_snapshotted_once_even_with_a_metadata_cycle(
    tmp_path: Path,
) -> None:
    root = build(tmp_path / "ui")
    manifest = json.loads((root / ".vite/manifest.json").read_text())
    manifest["index.html"]["imports"] = ["shared"]
    manifest["shared"] = {
        "file": "assets/shared.js",
        "imports": ["index.html"],
        "isDynamicEntry": True,
    }
    (root / "assets/shared.js").write_text("export const shared = true;")
    (root / ".vite/manifest.json").write_text(json.dumps(manifest))
    (root / "index.html").write_text(
        HTML.replace("</head>", '<link rel="modulepreload" href="./assets/shared.js"></head>')
    )
    bundle = load_bundle(root)
    assert bundle is not None and len(bundle.assets) == 3


@pytest.mark.parametrize("data", [" \n", "bad()"])
def test_external_module_allows_whitespace_but_never_inline_executable_data(
    tmp_path: Path, data: str
) -> None:
    root = build(tmp_path / "ui")
    (root / "index.html").write_text(
        HTML.replace(
            'src="./assets/index-safe.js"></script>',
            'src="./assets/index-safe.js">' + data + "</script>",
        )
    )
    if data.strip():
        with pytest.raises(StorageFailure):
            load_bundle(root)
    else:
        assert load_bundle(root) is not None


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"index.html": {}},
        {"index.html": {"file": "../private.js", "isEntry": True}},
        {"index.html": {"file": "https://foreign.invalid/code.js", "isEntry": True}},
        {"index.html": {"file": "assets/index-safe.js", "isEntry": False}},
        {"index.html": {"file": "assets/index-safe.js", "isEntry": 1}},
        {"index.html": {"file": "assets/index-safe.js", "isEntry": True, "unexpected": True}},
        {"index.html": {"file": "assets/index-safe.js", "isEntry": True, "css": ["../x.css"]}},
        {"index.html": {"file": "assets/index-safe.js", "isEntry": True, "imports": ["missing"]}},
    ],
)
def test_manifest_cannot_choose_an_unregistered_source_or_shape(
    tmp_path: Path, value: object
) -> None:
    root = build(tmp_path / "ui")
    (root / ".vite/manifest.json").write_text(json.dumps(value))
    with pytest.raises(StorageFailure, match="ui_bundle_unavailable"):
        load_bundle(root)


@pytest.mark.parametrize(
    "change",
    [
        "missing_js",
        "extra_file",
        "symlink",
        "invalid_utf8",
        "oversized_js",
        "duplicate_key",
        "malformed_json",
    ],
)
def test_incomplete_or_unsafe_build_fails_closed(tmp_path: Path, change: str) -> None:
    root = build(tmp_path / "ui")
    js = root / "assets/index-safe.js"
    if change == "missing_js":
        js.unlink()
    elif change == "extra_file":
        (root / "private.json").write_text('{"private":true}')
    elif change == "symlink":
        js.unlink()
        js.symlink_to(tmp_path / "outside.js")
    elif change == "invalid_utf8":
        js.write_bytes(b"\xff")
    elif change == "oversized_js":
        js.write_bytes(b"x" * (1_048_576 + 1))
    elif change == "duplicate_key":
        (root / ".vite/manifest.json").write_text('{"index.html":{},"index.html":{}}')
    else:
        (root / ".vite/manifest.json").write_text("not json")
    with pytest.raises(StorageFailure, match="ui_bundle_unavailable"):
        load_bundle(root)


@pytest.mark.parametrize(
    "replacement",
    [
        HTML.replace("__DOMUS_BOOTSTRAP_V1__", "private content"),
        HTML.replace("__DOMUS_BOOTSTRAP_V1__", "__DOMUS_BOOTSTRAP_V1____DOMUS_BOOTSTRAP_V1__"),
        HTML.replace('src="./assets/index-safe.js"', 'src="https://foreign.invalid/evil.js"'),
        HTML.replace('type="module"', 'type="module" onload="bad()"'),
        HTML.replace("</head>", '<base href="https://foreign.invalid/"></head>'),
        HTML.replace("</head>", "<script>bad()</script></head>"),
        HTML.replace('id="domus-entry"', 'id="other"'),
    ],
)
def test_shell_has_one_inert_bootstrap_and_only_registered_external_resources(
    tmp_path: Path, replacement: str
) -> None:
    root = build(tmp_path / "ui")
    (root / "index.html").write_text(replacement)
    with pytest.raises(StorageFailure, match="ui_bundle_unavailable"):
        load_bundle(root)
