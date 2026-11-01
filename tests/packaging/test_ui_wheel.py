"""Verify the actual built wheel, including ignored UI resources and fixture exclusion."""

import hashlib
from pathlib import Path
from zipfile import ZipFile

from domus.entrypoints.ui_bundle import load_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_built_wheel_contains_exact_product_bundle_and_no_browser_fixture(tmp_path: Path) -> None:
    wheels = list((ROOT / "dist").glob("domus_server-*.whl"))
    assert len(wheels) == 1, "Build the current backend wheel before running package acceptance"
    build = ROOT / "backend/src/domus/ui"
    assert load_bundle(build) is not None
    expected = {
        "domus/ui/" + path.relative_to(build).as_posix(): path.read_bytes()
        for path in build.rglob("*")
        if path.is_file()
    }
    assert len(expected) >= 4
    with ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        assert len(names) == len(set(names))
        actual = {name: wheel.read(name) for name in names if name.startswith("domus/ui/")}
        assert {key: hashlib.sha256(value).hexdigest() for key, value in actual.items()} == {
            key: hashlib.sha256(value).hexdigest() for key, value in expected.items()
        }
        assert not any(name.startswith(("tests/", "frontend/")) for name in names)
        assert not any(b"__fixture__" in wheel.read(name) for name in names)
        for name, data in actual.items():
            target = tmp_path / name.removeprefix("domus/ui/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    assert load_bundle(tmp_path) == load_bundle(build)
