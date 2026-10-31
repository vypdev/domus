"""Run the native HA authentication preview on a Supervisor-only private listener."""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import uvicorn
from fastapi import FastAPI, Request

from domus.application.household_commands import HouseholdCommands
from domus.application.household_queries import HouseholdQueries
from domus.application.member_commands import MemberCommands
from domus.application.policy_commands import PolicyCommands
from domus.application.recovery_commands import RecoveryCommands, RecoveryQueries
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.household_http import HouseholdHTTPContext
from domus.entrypoints.ingress_http import create_ingress_app
from domus.entrypoints.native_http import NativeHTTPContext, create_native_app
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.auth_runtime import MonotonicClock, SecureEntropy
from domus.infrastructure.ha_config import HAEndpoint, PublicOrigins
from domus.infrastructure.ha_directory import HomeAssistantDirectory
from domus.infrastructure.ha_ingress import SupervisorIdentity
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket
from domus.infrastructure.ingress_sessions import IngressSessions
from domus.infrastructure.owned_storage import OwnedStorage, open_storage
from domus.infrastructure.sqlite import SQLiteDatabase


@dataclass
class NativeRuntime:
    app: FastAPI
    sessions: IngressSessions = field(repr=False)
    storage: OwnedStorage | None = field(default=None, repr=False)

    def close(self) -> None:
        try:
            self.sessions.close()
        finally:
            if self.storage is not None:
                self.storage.close()


def create_owned_runtime(
    token: str, channel: str, data_directory: Path, public_origins: tuple[str, ...]
) -> NativeRuntime:
    origins = PublicOrigins(public_origins).values
    identity = SupervisorIdentity(HomeAssistantWebSocket(HAEndpoint.supervisor()), token)
    storage = open_storage(data_directory, channel)
    try:
        runtime = _compose_business(identity, storage.database, origins)
        runtime.storage = storage
        return runtime
    except BaseException:
        storage.close()
        raise


def create_business_runtime(
    token: str,
    channel: str,
    database: Path,
    instance_id: str,
    public_origins: tuple[str, ...],
) -> NativeRuntime:
    installation = Installation(instance_id, channel)
    origins = PublicOrigins(public_origins).values
    identity = SupervisorIdentity(HomeAssistantWebSocket(HAEndpoint.supervisor()), token)
    store = SQLiteDatabase(database, installation)
    store.initialize()
    return _compose_business(identity, store, origins)


def _compose_business(
    identity: SupervisorIdentity, store: SQLiteDatabase, origins: tuple[str, ...]
) -> NativeRuntime:
    clock, entropy = MonotonicClock(), SecureEntropy()
    sessions = IngressSessions(
        identity, store.installation, clock, entropy, entropy.new().encode("ascii")
    )
    directory = HomeAssistantDirectory(identity.lookup, identity.transport_token)
    utc, identifiers, zones = SystemClock(), SecureIdentifiers(), TimeZoneCatalog()

    def context(request: Request) -> NativeHTTPContext:
        peer = cast(tuple[str, int], request.scope["client"])
        actor = sessions.request(
            peer[0],
            tuple(
                (key.decode("latin1"), value.decode("latin1"))
                for key, value in request.scope["headers"]
            ),
        )
        services = HouseholdHTTPContext(
            lambda: HouseholdQueries(store, actor.read()),
            HouseholdCommands(store, actor, directory, zones, utc, identifiers),
            MemberCommands(store, actor, directory, utc, identifiers),
            PolicyCommands(store, actor, directory, utc, identifiers),
            RecoveryCommands(store, actor, store.installation, utc, identifiers),
            lambda: RecoveryQueries(store, actor.read(), store.installation, utc),
        )
        return NativeHTTPContext(services, actor.status, actor.csrf, actor.verify_csrf)

    app = create_native_app(
        context,
        origins,
        store.installation.channel,
        clock,
        correlation=lambda: "cor_" + entropy.new(),
    )
    return NativeRuntime(app, sessions)


def create_runtime(token: str, channel: str) -> FastAPI:
    identity = SupervisorIdentity(HomeAssistantWebSocket(HAEndpoint.supervisor()), token)
    entropy = SecureEntropy()
    return create_ingress_app(identity.prove, channel, correlation=lambda: "cor_" + entropy.new())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Domus behind private Home Assistant Ingress.")
    parser.add_argument("--channel", required=True, choices=("stable", "edge"))
    data = parser.add_mutually_exclusive_group()
    data.add_argument("--database", type=Path)
    data.add_argument("--data-directory", type=Path)
    parser.add_argument("--instance-id")
    parser.add_argument("--public-origin", action="append", default=[])
    args = parser.parse_args(argv)
    token = os.environ.pop("SUPERVISOR_TOKEN", "")
    runtime = None
    try:
        if args.data_directory is not None:
            if args.instance_id or not args.public_origin:
                raise InvalidInput("invalid_persistent_configuration")
            runtime = create_owned_runtime(
                token, args.channel, args.data_directory, tuple(args.public_origin)
            )
            app = runtime.app
        elif args.database is not None:
            if not args.instance_id or not args.public_origin:
                raise InvalidInput("invalid_persistent_configuration")
            runtime = create_business_runtime(
                token, args.channel, args.database, args.instance_id, tuple(args.public_origin)
            )
            app = runtime.app
        else:
            if args.instance_id or args.public_origin:
                raise InvalidInput("invalid_persistent_configuration")
            app = create_runtime(token, args.channel)
    except DomusError:
        print(
            "Start Domus as a Home Assistant app with valid configuration and owned data. "
            "Existing household records are retained.",
            file=sys.stderr,
        )
        return 2
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8099,
            workers=1,
            proxy_headers=False,
            forwarded_allow_ips="",
            access_log=False,
            server_header=False,
            log_level="warning",
            limit_concurrency=64,
            timeout_keep_alive=5,
            timeout_graceful_shutdown=10,
            h11_max_incomplete_event_size=65_536,
        )
    finally:
        if runtime is not None:
            runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
