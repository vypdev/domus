"""Compose standalone authentication and optional private SQLite household services."""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from domus.application.authentication import Authentication
from domus.application.sessions import SessionGuard
from domus.composition.household import standalone_context
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.http import HTTPSettings, create_app
from domus.infrastructure.auth_runtime import MonotonicClock, SecureEntropy
from domus.infrastructure.ha_config import HAEndpoint, OAuthConfiguration
from domus.infrastructure.ha_http import HomeAssistantOAuth
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket
from domus.infrastructure.memory_attempts import MemoryLoginAttempts
from domus.infrastructure.owned_storage import OwnedStorage, open_storage, reject_owned_database
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.standalone_sessions import StandaloneIdentity


@dataclass
class AuthenticationRuntime:
    app: FastAPI
    identity: StandaloneIdentity = field(repr=False)
    storage: OwnedStorage | None = field(default=None, repr=False)

    def close(self) -> tuple[int, int]:
        try:
            return self.identity.shutdown()
        finally:
            if self.storage is not None:
                self.storage.close()


def create_owned_runtime(
    ha_origin: str,
    public_origin: str,
    channel: str,
    data_directory: Path,
    *,
    development_http: bool = False,
) -> AuthenticationRuntime:
    config = OAuthConfiguration(HAEndpoint(ha_origin), public_origin, development_http)
    storage = open_storage(data_directory, channel)
    try:
        runtime = _compose(config, storage.installation, storage.database)
        runtime.storage = storage
        return runtime
    except BaseException:
        storage.close()
        raise


def create_runtime(
    ha_origin: str,
    public_origin: str,
    instance_id: str,
    channel: str,
    *,
    development_http: bool = False,
    database: Path | None = None,
) -> AuthenticationRuntime:
    installation = Installation(instance_id, channel)
    config = OAuthConfiguration(HAEndpoint(ha_origin), public_origin, development_http)
    store = None
    if database is not None:
        reject_owned_database(database)
        store = SQLiteDatabase(database, installation)
        store.initialize()
    return _compose(config, installation, store)


def _compose(
    config: OAuthConfiguration, installation: Installation, store: SQLiteDatabase | None
) -> AuthenticationRuntime:
    clock, entropy = MonotonicClock(), SecureEntropy()
    identity = StandaloneIdentity(
        HomeAssistantOAuth(config), HomeAssistantWebSocket(config.ha), clock
    )
    authentication = Authentication(MemoryLoginAttempts(), identity, clock, entropy)
    tag = f"domus-{installation.channel}-{installation.instance_id.replace('-', '')[:12]}"
    settings = HTTPSettings(config.public_origin, tag, entropy.new().encode("ascii"))
    guard = SessionGuard(identity, identity, clock)
    context = None
    if store is not None:
        context = standalone_context(store, guard, identity, installation)
    app = create_app(
        authentication,
        guard,
        identity,
        settings,
        correlation=lambda: "cor_" + entropy.new(),
        household_context=context,
    )
    return AuthenticationRuntime(app, identity)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Domus standalone; --data-directory manages persistent household data."
    )
    parser.add_argument("--ha-url", required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--instance-id")
    parser.add_argument("--channel", choices=("stable", "edge"), required=True)
    parser.add_argument("--development-http", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    data = parser.add_mutually_exclusive_group()
    data.add_argument(
        "--database", type=Path, help="Owned SQLite file; parent directory must exist."
    )
    data.add_argument("--data-directory", type=Path, help="Existing private 0700 data directory.")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise InvalidInput("invalid_bind_port")
        if args.development_http and args.host not in ("127.0.0.1", "::1"):
            raise InvalidInput("development_requires_loopback")
        if args.data_directory is not None:
            if args.instance_id is not None:
                raise InvalidInput("invalid_persistent_configuration")
            runtime = create_owned_runtime(
                args.ha_url,
                args.public_origin,
                args.channel,
                args.data_directory,
                development_http=args.development_http,
            )
        else:
            if not args.instance_id:
                raise InvalidInput("invalid_persistent_configuration")
            runtime = create_runtime(
                args.ha_url,
                args.public_origin,
                args.instance_id,
                args.channel,
                development_http=args.development_http,
                database=args.database,
            )
    except DomusError as error:
        print(f"Configuration rejected: {error.code}", file=sys.stderr)
        return 2
    try:
        uvicorn.run(
            runtime.app,
            host=args.host,
            port=args.port,
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
        revoked, unrevoked = runtime.close()
        logging.getLogger("domus.auth").info(
            "auth_runtime_stopped revoked=%d unconfirmed=%d", revoked, unrevoked
        )
        if unrevoked:
            logging.getLogger("domus.auth").warning("ha_grants_not_revoked: %d", unrevoked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
