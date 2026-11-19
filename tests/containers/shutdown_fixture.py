"""Observe real CLI shutdown with isolated records and a disposable identity provider."""

import json
import sys
import time
from pathlib import Path

from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CreateTask
from domus.composition import ingress, server
from domus.domain.errors import IdentityUnavailable
from domus.domain.identity import HumanIdentity
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.ha_http import OAuthTokens

STARTED = Path("/tmp/domus-shutdown-started.json")
CLOSING = Path("/tmp/domus-shutdown-closing")
RELEASE = Path("/tmp/domus-shutdown-release")
FINISHED = Path("/tmp/domus-shutdown-finished.json")
SESSIONS = tuple(f"shutdown_session_{index}" for index in range(3))


class Actor:
    def current(self):
        return HumanIdentity("shutdown-fixture-admin", True, True, False)

    def get(self, _identifier):
        raise AssertionError("The seed uses the verified fixture administrator")


class DisposableOAuth:
    def __init__(self, configuration):
        self.configuration = configuration
        self.issued = 0
        self.revoke_calls = 0
        self.identity = None

    def exchange(self, _code, _verifier):
        self.issued += 1
        return OAuthTokens(
            f"fixture-access-{self.issued}", f"fixture-refresh-{self.issued}", 3600, "fixture"
        )

    def revoke(self, _refresh):
        assert all(self.identity.get(session) is None for session in SESSIONS)
        self.revoke_calls += 1
        if self.revoke_calls == 2:
            raise IdentityUnavailable("fixture_provider_unavailable")


class DisposableSocket:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def current_user(self, _tokens):
        return Actor().current()


def seed(runtime):
    storage = runtime.storage
    actor, clock, identifiers = Actor(), SystemClock(), SecureIdentifiers()
    HouseholdCommands(storage.database, actor, actor, TimeZoneCatalog(), clock, identifiers).setup(
        "shutdown-household", SetupHousehold("Shutdown fixture", "UTC")
    )
    receipt = TaskCommands(storage.database, actor, clock, identifiers).create(
        "shutdown-task", CreateTask(TaskContent("Retained shutdown task"))
    )
    STARTED.write_text(
        json.dumps(
            {
                "instance": storage.installation.instance_id,
                "operation": receipt.operation_id,
                "result": receipt.result.decode(),
            }
        )
    )


def observe_runtime(factory, standalone):
    def create(*args, **kwargs):
        runtime = factory(*args, **kwargs)
        seed(runtime)
        if standalone:
            identity = runtime.identity
            identity.oauth.identity = identity
            now = identity.clock.now()
            for session in SESSIONS:
                identity.sign_in("fixture-code", "v" * 43, session, now, now + 60_000)
        return runtime

    return create


def observe_close(original, standalone):
    def close(runtime):
        workers_stopped = not runtime.recurrence.is_running and not runtime.points_worker.is_running
        CLOSING.write_text("runtime cleanup entered")
        deadline = time.monotonic() + 8
        while not RELEASE.exists():
            if time.monotonic() >= deadline:
                raise AssertionError("The test did not release its shutdown gate")
            time.sleep(0.02)
        result = original(runtime)
        report = {"workers_stopped": workers_stopped, "result": result}
        if standalone:
            report["revoke_calls"] = runtime.identity.oauth.revoke_calls
            report["local_sessions_removed"] = all(
                runtime.identity.get(session) is None for session in SESSIONS
            )
        FINISHED.write_text(json.dumps(report))
        return result

    return close


if __name__ == "__main__":
    for marker in (STARTED, CLOSING, RELEASE, FINISHED):
        marker.unlink(missing_ok=True)
    standalone = Path(sys.argv[0]).name == "domus-server"
    module = server if standalone else ingress
    runtime_type = server.AuthenticationRuntime if standalone else ingress.NativeRuntime
    if standalone:
        server.HomeAssistantOAuth = DisposableOAuth
        server.HomeAssistantWebSocket = DisposableSocket
    module.create_owned_runtime = observe_runtime(module.create_owned_runtime, standalone)
    runtime_type.close = observe_close(runtime_type.close, standalone)
    raise SystemExit(module.main())
