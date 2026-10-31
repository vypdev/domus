"""Supervisor composition owns its private endpoint and never asks for a human token."""

import runpy
import sys

import pytest
from fastapi.testclient import TestClient

from domus.composition import ingress


def test_composition_exposes_only_loopback_process_health_without_upstream_calls() -> None:
    app = ingress.create_runtime("private-supervisor-token", "edge")
    client = TestClient(app, client=("127.0.0.1", 1234))
    assert client.get("/health").json() == {"status": "ready", "scope": "process"}
    assert client.get("/").status_code == 403


def test_cli_keeps_real_peer_and_private_listener_security(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "private-supervisor-token")
    calls = []
    monkeypatch.setattr(ingress.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert ingress.main(["--channel", "edge"]) == 0
    assert "SUPERVISOR_TOKEN" not in ingress.os.environ
    assert calls == [
        {
            "host": "0.0.0.0",
            "port": 8099,
            "workers": 1,
            "proxy_headers": False,
            "forwarded_allow_ips": "",
            "access_log": False,
            "server_header": False,
            "log_level": "warning",
            "limit_concurrency": 64,
            "timeout_keep_alive": 5,
            "timeout_graceful_shutdown": 10,
            "h11_max_incomplete_event_size": 65_536,
        }
    ]


@pytest.mark.parametrize("token", [None, "invalid token"])
def test_cli_missing_or_malformed_supervisor_configuration_fails_without_secret_output(
    token: str | None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    if token is not None:
        monkeypatch.setenv("SUPERVISOR_TOKEN", token)
    assert ingress.main(["--channel", "edge"]) == 2
    output = capsys.readouterr()
    assert "Home Assistant app" in output.err
    assert "invalid token" not in output.err


def test_module_command_help_requires_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "domus.composition.ingress", raising=False)
    monkeypatch.setattr(sys, "argv", ["domus-ingress", "--help"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("domus.composition.ingress", run_name="__main__")
    assert stopped.value.code == 0
