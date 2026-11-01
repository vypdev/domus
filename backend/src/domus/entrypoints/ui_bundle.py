"""Snapshot a bounded packaged Vite build; requests never resolve filesystem paths."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType

from domus.domain.errors import StorageFailure

BOOTSTRAP_SLOT = "__DOMUS_BOOTSTRAP_V1__"
_ASSET = re.compile(r"assets/[A-Za-z0-9_][A-Za-z0-9_.-]{0,160}\.(js|css)")
_MIME = {"js": "text/javascript", "css": "text/css"}


def _require(value: object) -> None:
    if not value:
        raise ValueError("invalid_ui_bundle")


def _read(path: Path, maximum: int) -> bytes:
    _require(not path.is_symlink() and path.is_file() and path.stat().st_size <= maximum)
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    _require(len(data) <= maximum)
    return data


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _inventory(root: Path) -> set[str]:
    files: set[str] = set()
    pending = [root]
    total = 0
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            _require(not path.is_symlink())
            if path.is_dir():
                _require(directory == root and path.name in ("assets", ".vite"))
                pending.append(path)
            else:
                _require(path.is_file())
                files.add(path.relative_to(root).as_posix())
                total += path.stat().st_size
                _require(len(files) <= 66 and total <= 4_194_304)
    return files


class _Shell(HTMLParser):
    def __init__(self, assets: set[str], entry: str, css: list[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.assets, self.entry, self.css = assets, entry, css
        self.kind: str | None = None
        self.bootstrap: list[str] = []
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.roots = self.bootstraps = self.doctypes = 0

    def handle_decl(self, decl: str) -> None:
        _require(decl.lower() == "doctype html")
        self.doctypes += 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        _require(len(values) == len(attrs))
        _require(
            tag in ("html", "head", "meta", "title", "script", "link", "body", "div", "noscript")
        )
        _require(not any(key.startswith("on") or key == "style" for key in values))
        _require("http-equiv" not in values)
        if tag == "div" and values.get("id") == "domus-entry":
            self.roots += 1
        if tag == "script":
            _require(self.kind is None)
            if values.get("type") == "application/json":
                _require(values.get("id") == "domus-bootstrap" and "src" not in values)
                self.kind = "bootstrap"
                self.bootstraps += 1
            else:
                _require(values.get("type") == "module")
                _require(values.get("src") == "./" + self.entry)
                self.scripts.append(self.entry)
                self.kind = "module"
        elif tag == "link":
            path = values.get("href")
            _require(isinstance(path, str) and path.startswith("./"))
            path = str(path)[2:]
            _require(path in self.assets)
            if values.get("rel") == "stylesheet":
                _require(path.endswith(".css"))
                self.styles.append(path)
            else:
                _require(values.get("rel") == "modulepreload" and path.endswith(".js"))
        else:
            _require("src" not in values and "href" not in values)

    def handle_data(self, data: str) -> None:
        if self.kind == "bootstrap":
            self.bootstrap.append(data)
        elif self.kind == "module":
            _require(not data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.kind = None

    def verify(self, template: str) -> None:
        self.feed(template)
        self.close()
        _require(self.kind is None and self.doctypes == self.roots == self.bootstraps == 1)
        _require("".join(self.bootstrap) == BOOTSTRAP_SLOT and template.count(BOOTSTRAP_SLOT) == 1)
        _require(self.scripts == [self.entry] and sorted(self.styles) == sorted(self.css))


@dataclass(frozen=True, slots=True)
class UIBundle:
    template: str
    assets: Mapping[str, tuple[bytes, str]]


def load_bundle(root: Path) -> UIBundle | None:
    if not root.exists() and not root.is_symlink():
        return None
    try:
        _require(not root.is_symlink() and root.is_dir())
        inventory = _inventory(root)
        manifest = json.loads(
            _read(root / ".vite/manifest.json", 65_536), object_pairs_hook=_object
        )
        _require(type(manifest) is dict and 1 <= len(manifest) <= 64 and "index.html" in manifest)
        pending, seen, assets = ["index.html"], set(), set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            item = manifest[key]
            _require(type(item) is dict)
            _require(
                set(item)
                <= {
                    "file",
                    "name",
                    "src",
                    "isEntry",
                    "isDynamicEntry",
                    "css",
                    "assets",
                    "imports",
                    "dynamicImports",
                }
            )
            path = item.get("file")
            _require(isinstance(path, str) and _ASSET.fullmatch(path) and path.endswith(".js"))
            assets.add(path)
            if key == "index.html":
                _require(item.get("isEntry") is True)
            for flag in ("isEntry", "isDynamicEntry"):
                _require(flag not in item or type(item[flag]) is bool)
            for text in ("name", "src"):
                _require(
                    text not in item or (type(item[text]) is str and 0 < len(item[text]) <= 512)
                )
            for kind in ("css", "assets", "imports", "dynamicImports"):
                links = item.get(kind, [])
                _require(
                    type(links) is list
                    and len(links) <= 64
                    and all(type(link) is str for link in links)
                )
                _require(len(links) == len(set(links)))
                for link in links:
                    if kind in ("imports", "dynamicImports"):
                        _require(link in manifest)
                        pending.append(link)
                    else:
                        _require(_ASSET.fullmatch(link))
                        _require(kind != "css" or link.endswith(".css"))
                        assets.add(link)
        _require(seen == set(manifest))
        _require(inventory == {"index.html", ".vite/manifest.json"} | assets)
        template = _read(root / "index.html", 65_536).decode("utf-8")
        _Shell(
            assets, manifest["index.html"]["file"], manifest["index.html"].get("css", [])
        ).verify(template)
        content = {}
        for path in sorted(assets):
            data = _read(root / path, 1_048_576)
            data.decode("utf-8")
            content[path] = (data, _MIME[path.rsplit(".", 1)[1]])
        return UIBundle(template, MappingProxyType(content))
    except OSError, ValueError, TypeError, KeyError, UnicodeError:
        raise StorageFailure("ui_bundle_unavailable") from None
