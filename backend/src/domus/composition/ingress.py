"""Run the native HA authentication preview on a Supervisor-only private listener."""

import argparse
import os
import sys

import uvicorn
from fastapi import FastAPI

from domus.domain.errors import DomusError
from domus.entrypoints.ingress_http import create_ingress_app
from domus.infrastructure.auth_runtime import SecureEntropy
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_ingress import SupervisorIdentity
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket


def create_runtime(token: str, channel: str) -> FastAPI:
    identity = SupervisorIdentity(HomeAssistantWebSocket(HAEndpoint.supervisor()), token)
    entropy = SecureEntropy()
    return create_ingress_app(identity.prove, channel, correlation=lambda: "cor_" + entropy.new())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Domus native HA authentication preview.")
    parser.add_argument("--channel", required=True, choices=("stable", "edge"))
    args = parser.parse_args(argv)
    token = os.environ.pop("SUPERVISOR_TOKEN", "")
    try:
        app = create_runtime(token, args.channel)
    except DomusError:
        print("Start this runtime as a Home Assistant app with Core API access.", file=sys.stderr)
        return 2
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
