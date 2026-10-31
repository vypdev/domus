"""Provision only the packaged app's private child, drop privilege, then exec Ingress."""

import argparse
import os
import stat
import sys
from pathlib import Path
from typing import cast

from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import JsonDocument
from domus.infrastructure.ha_config import PublicOrigins
from domus.infrastructure.ha_http import _secret

_DATA_ROOT = Path("/data")
_ROOT_UID = 0
_RUNTIME_UID = _RUNTIME_GID = 65532
_ENTRYPOINT = "/app/.venv/bin/domus-ingress"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _options(directory: int) -> tuple[str, ...]:
    descriptor = os.open(
        "options.json",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        dir_fd=directory,
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != _ROOT_UID
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise InvalidInput("unsafe_app_options")
        content = os.read(descriptor, 16_385)
    finally:
        os.close(descriptor)
    if len(content) > 16_384:
        raise InvalidInput("invalid_app_options")
    value = JsonDocument(content.decode("utf-8")).decode()
    if set(value) != {"public_origins"} or type(value["public_origins"]) is not list:
        raise InvalidInput("invalid_app_options")
    return PublicOrigins(tuple(cast(list[str], value["public_origins"]))).values


def _provision(directory: int) -> None:
    created = False
    try:
        os.mkdir("domus", mode=0o700, dir_fd=directory)
        created = True
    except FileExistsError:
        pass
    descriptor = os.open("domus", _DIRECTORY_FLAGS, dir_fd=directory)
    try:
        if created:
            os.fchown(descriptor, _RUNTIME_UID, _RUNTIME_GID)
            os.fsync(descriptor)
            os.fsync(directory)
        info = os.fstat(descriptor)
        if (
            info.st_uid != _RUNTIME_UID
            or info.st_gid != _RUNTIME_GID
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise InvalidInput("unsafe_app_data")
    finally:
        os.close(descriptor)


def _drop_privileges() -> None:
    os.setgroups([])
    os.setgid(_RUNTIME_GID)
    os.setuid(_RUNTIME_UID)
    if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (
        _RUNTIME_UID,
        _RUNTIME_UID,
        _RUNTIME_GID,
        _RUNTIME_GID,
    ) or os.getgroups():
        raise InvalidInput("runtime_identity_failure")


def _run(channel: str) -> None:
    if (os.getuid(), os.geteuid()) != (_ROOT_UID, _ROOT_UID):
        raise InvalidInput("packaged_app_required")
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    _secret(token)
    os.umask(0o077)
    directory = os.open(_DATA_ROOT, _DIRECTORY_FLAGS)
    try:
        info = os.fstat(directory)
        if info.st_uid != _ROOT_UID or stat.S_IMODE(info.st_mode) & 0o022:
            raise InvalidInput("unsafe_app_data_parent")
        origins = _options(directory)
        _provision(directory)
    finally:
        os.close(directory)
    _drop_privileges()
    arguments = [_ENTRYPOINT, "--channel", channel, "--data-directory", str(_DATA_ROOT / "domus")]
    for origin in origins:
        arguments.extend(("--public-origin", origin))
    os.execve(
        _ENTRYPOINT,
        arguments,
        {
            "PATH": "/app/.venv/bin:/usr/local/bin:/usr/bin:/bin",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
            "SUPERVISOR_TOKEN": token,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the packaged Domus Home Assistant app.")
    parser.add_argument("--channel", required=True, choices=("stable", "edge"))
    args = parser.parse_args(argv)
    try:
        _run(args.channel)
    except DomusError, OSError, UnicodeError:
        print(
            "Domus could not start. Review the app's public_origins and private data ownership. "
            "Existing household records are retained.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
