"""The local authentication composition fixes listener, proxy and credential cleanup policy."""

import runpy
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_standalone_sessions import TOKENS, sign_in
from test_standalone_sessions import fixture as identity_fixture

from domus.composition import server
from domus.domain.errors import IdentityRejected

INSTANCE = "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6"


def arguments() -> list[str]:
    return [
        "--ha-url",
        "http://homeassistant.local:8123",
        "--public-origin",
        "http://127.0.0.1:8099",
        "--instance-id",
        INSTANCE,
        "--channel",
        "edge",
        "--development-http",
    ]


def test_composition_builds_fixed_edge_authentication_without_creating_household_data() -> None:
    runtime = server.create_runtime(
        "http://homeassistant.local:8123",
        "http://127.0.0.1:8099",
        INSTANCE,
        "edge",
        development_http=True,
    )
    with TestClient(
        runtime.app, base_url="http://127.0.0.1:8099", follow_redirects=False
    ) as client:
        assert client.get("/api/v1/session").status_code == 401
        response = client.get("/api/v1/auth/start")
        assert response.status_code == 303
        assert response.headers["location"].startswith(
            "http://homeassistant.local:8123/auth/authorize?"
        )
        assert "Secure" not in response.headers["set-cookie"]
        assert "domus-edge-047cc6fbdfb0" in response.headers["set-cookie"]
    assert runtime.close() == (0, 0)


def test_server_uses_one_worker_no_access_query_logging_and_no_proxy_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []

    @dataclass
    class Runtime:
        app: object = None

        def close(self) -> tuple[int, int]:
            events.append("closed")
            return 0, 0

    def create(*args: object, **kwargs: object) -> Runtime:
        return Runtime()

    def run(app: object, **kwargs: object) -> None:
        assert kwargs == {
            "host": "127.0.0.1",
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
        events.append("ran")

    monkeypatch.setattr(server, "create_runtime", create)
    monkeypatch.setattr(server.uvicorn, "run", run)
    assert server.main(arguments()) == 0
    assert events == ["ran", "closed"]


def test_startup_failure_still_cleans_owned_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = server.create_runtime("http://ha.local", "https://domus.example", INSTANCE, "edge")
    closed = []
    monkeypatch.setattr(server, "create_runtime", lambda *args, **kwargs: runtime)

    def cleanup() -> tuple[int, int]:
        closed.append(True)
        return 0, 0

    monkeypatch.setattr(runtime, "close", cleanup)

    def failed(*args: object, **kwargs: object) -> None:
        raise RuntimeError("listener failed")

    monkeypatch.setattr(server.uvicorn, "run", failed)
    with pytest.raises(RuntimeError):
        server.main(arguments())
    assert closed == [True]


def test_unrevoked_shutdown_count_is_reported_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = server.create_runtime("http://ha.local", "https://domus.example", INSTANCE, "edge")
    monkeypatch.setattr(server, "create_runtime", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(runtime, "close", lambda: (0, 1))
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: None)
    assert server.main(arguments()) == 0
    assert "ha_grants_not_revoked: 1" in caplog.text
    assert "private-access" not in caplog.text


@pytest.mark.parametrize(
    "extra",
    [["--port", "0"], ["--port", "65536"], ["--host", "0.0.0.0"], ["--instance-id", "not-a-uuid"]],
)
def test_bad_configuration_does_not_start_a_listener(
    extra: list[str], capsys: pytest.CaptureFixture
) -> None:
    assert server.main(arguments() + extra) == 2
    assert "Configuration rejected:" in capsys.readouterr().err


def test_console_help_is_a_real_module_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["domus-server", "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(server.__file__)), run_name="__main__")
    assert result.value.code == 0


def test_shutdown_clears_all_local_leases_and_bounds_remote_cleanup() -> None:
    identity, oauth, _, _ = identity_fixture()
    for index in range(3):
        from dataclasses import replace

        oauth.issued = replace(
            TOKENS, access_token=f"private-access-{index}", refresh_token=f"private-refresh-{index}"
        )
        sign_in(identity, f"session_{index}")
    assert identity.shutdown() == (2, 1)
    assert len(oauth.revoked) == 2
    for index in range(3):
        assert identity.get(f"session_{index}") is None
    with pytest.raises(IdentityRejected, match="server_closed"):
        sign_in(identity, "later_session")
    assert identity.shutdown() == (0, 0)


def test_shutdown_during_initial_proof_cannot_install_a_late_session() -> None:
    identity, oauth, socket, _ = identity_fixture()
    socket.callback = lambda: identity.shutdown()
    with pytest.raises(IdentityRejected, match="server_closed"):
        sign_in(identity)
    assert identity.get("session_1") is None
    assert oauth.revoked == ["private-refresh"]
