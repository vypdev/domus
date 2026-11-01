"""Run only in a disposable real image; no credentials or HA access are required."""

import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

import domus
from domus.entrypoints.ui_bundle import load_bundle

expected = json.loads(sys.argv[1])
root = Path(domus.__file__).parent / "ui"
bundle = load_bundle(root)
assert bundle is not None
actual = {
    p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in root.rglob("*")
    if p.is_file()
}
assert actual == expected, (actual, expected)
assert len(actual) == 4
assert not any(shutil.which(name) for name in ["node", "npm", "pnpm"])
assert importlib.util.find_spec("pytest") is None
assert importlib.util.find_spec("domus_tooling") is None
assert not any(b"__fixture__" in path.read_bytes() for path in root.rglob("*") if path.is_file())


def get(path, method="GET"):
    request = urllib.request.Request(
        "http://127.0.0.1:8099" + path, headers={"Host": "domus.fixture"}, method=method
    )
    return urllib.request.urlopen(request, timeout=3)


with get("/") as response:
    body = response.read().decode()
    assert response.status == 200 and response.headers.get("Set-Cookie") is None
    assert response.headers["Cache-Control"] == "no-store"
    policy = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert not any(value in policy for value in ["unsafe-inline", "unsafe-eval"])
match = re.search(r'type="application/json">([^<]+)</script>', body)
assert match
bootstrap = json.loads(match[1])
assert set(bootstrap) == {"version", "deployment", "application_base", "style_nonce"}
assert bootstrap["deployment"] == "standalone" and bootstrap["application_base"] == "/"
assert re.fullmatch("[A-Za-z0-9_-]{32}", bootstrap["style_nonce"])
paths = re.findall(r'(?:src|href)="(/assets/[^"<>]+)"', body)
assert len(paths) == 2 and len(set(paths)) == 2
for path in paths:
    with get(path) as response:
        data = response.read()
        assert response.status == 200
        assert hashlib.sha256(data).hexdigest() == expected[path[1:]]
        assert response.headers.get_content_type() == (
            "text/css" if path.endswith(".css") else "text/javascript"
        )
        assert response.headers["Cache-Control"] == "no-store"
    with get(path, "HEAD") as response:
        assert response.read() == b"" and int(response.headers["Content-Length"]) == len(data)
for path, status in [("/api/v1/session", 401), ("/assets/missing.js", 404)]:
    try:
        get(path)
    except urllib.error.HTTPError as error:
        assert error.code == status
        assert "script-src 'self'" not in error.headers["Content-Security-Policy"]
    else:
        raise AssertionError("Unavailable resource became shell success")
with sqlite3.connect("file:/data/domus/domus.sqlite3?mode=ro", uri=True) as connection:
    for table in ["households", "members", "receipts", "audit", "outbox"]:
        assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
print(
    json.dumps(
        {"ui_files": len(actual), "cookie_issued": False, "deployment": bootstrap["deployment"]}
    )
)
