"""Only the installation console selects restore paths and offline activation authority."""

import argparse
import json
from typing import TextIO

from domus.application.activation import ActivationCommands
from domus.application.ports import Clock
from domus.application.restoration import RestorationCommands
from domus.domain.errors import DatabaseRejected, InvalidInput
from domus.domain.storage import Installation, JsonObject
from domus.infrastructure.application_runtime import SecureIdentifiers
from domus.infrastructure.offline_storage import offline_storage
from domus.infrastructure.owned_storage import _metadata
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _directory


def execute(args: argparse.Namespace, outgoing: TextIO, clock: Clock) -> int:
    value: JsonObject
    if args.operation == "inspect":
        if args.data_directory is not None or args.database is not None or args.instance_id is None:
            raise InvalidInput("invalid_persistent_configuration")
        installation = Installation(args.instance_id, args.channel)
        archive = SQLiteRestorations(
            None, None, args.location, installation, clock, timeout=args.timeout
        )
        prepared = RestorationCommands(archive, installation, SecureIdentifiers()).inspect()
        value = {
            "state": "verified",
            "prepared": prepared.document().decode(),
            "message": "The private prepared restoration is verified. It is not active.",
            "action_required": (
                "Stop writes and activate only this bound preparation in its managed installation."
            ),
        }
    else:
        if args.data_directory is None or args.database is not None or args.instance_id is not None:
            raise InvalidInput("invalid_persistent_configuration")
        with _directory(args.data_directory, private=True) as directory:
            installation, state, _ = _metadata(directory)
        if installation.channel != args.channel or state != "ready":
            raise DatabaseRejected("installation_not_ready")
        if args.operation == "prepare":
            with offline_storage(args.data_directory, args.channel, timeout=args.timeout) as source:
                snapshot = SQLiteSnapshots(
                    None, args.snapshot, installation, clock, timeout=args.timeout
                ).inspect()
                archive = SQLiteRestorations(
                    source.database,
                    args.snapshot,
                    args.location,
                    installation,
                    clock,
                    snapshot,
                    timeout=args.timeout,
                )
                prepared = RestorationCommands(
                    archive, installation, SecureIdentifiers(), snapshot
                ).prepare()
            value = {
                "state": "prepared",
                "prepared": prepared.document().decode(),
                "message": "The isolated restoration is prepared and blocked from serving.",
                "action_required": "Inspect this exact preparation before offline activation.",
            }
        else:
            location = args.location if args.operation == "activate" else None
            restore_id = args.restore_id if args.operation in ("resume", "status") else None
            activation_prepared = (
                SQLiteRestorations(
                    None, None, location, installation, clock, timeout=args.timeout
                ).inspect()
                if location is not None
                else None
            )
            adapter = SQLiteActivation(
                args.data_directory, installation, clock, location, restore_id, timeout=args.timeout
            )
            commands = ActivationCommands(adapter, installation, activation_prepared, restore_id)
            result = (
                commands.activate()
                if args.operation == "activate"
                else commands.resume()
                if args.operation == "resume"
                else commands.inspect()
            )
            value = result.document().decode()
            value["message"] = {
                "active": "Activation completed. Its generation is selected; later work may exist.",
                "historical": (
                    "This activation completed previously. "
                    "Another generation is selected; no data was switched."
                ),
                "pending": "Activation is pending or uncertain. Normal startup remains blocked.",
            }[result.state]
            value["action_required"] = (
                "Inspect the current state before any further restore."
                if result.state != "pending"
                else "Resume the same activation ID. Keep existing installation data."
            )
    outgoing.write(json.dumps(value, ensure_ascii=True) + "\n")
    outgoing.flush()
    return 0
