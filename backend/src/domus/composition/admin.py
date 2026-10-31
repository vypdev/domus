"""Installation-console composition can approve recovery; it cannot complete human proof."""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from domus.application.recovery_commands import RecoveryConsole
from domus.application.snapshots import SnapshotCommands
from domus.composition.restore import execute as restore
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.console_recovery import TerminalRecoveryConfirmation
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.owned_storage import OwnedStorage, attach_database, attach_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def _snapshot(
    args: argparse.Namespace,
    database: SQLiteDatabase | None,
    installation: Installation,
    outgoing: TextIO,
) -> int:
    archive = SQLiteSnapshots(
        database, args.location, installation, SystemClock(), timeout=args.timeout
    )
    commands = SnapshotCommands(archive, installation, SecureIdentifiers())
    result = commands.create() if args.operation == "create" else commands.inspect()
    outgoing.write(
        json.dumps(
            {
                "state": "created" if args.operation == "create" else "verified",
                "snapshot": result.document().decode(),
                "message": "The private SQLite snapshot and its checkpoint metadata are verified.",
                "action_required": (
                    "Keep the bundle private. Inspect it again before preparing a restore."
                ),
            },
            ensure_ascii=True,
        )
        + "\n"
    )
    outgoing.flush()
    return 0


def main(
    argv: list[str] | None = None,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Manage the exact Domus installation from its console."
    )
    parser.add_argument("--channel", choices=("stable", "edge"), required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data-directory", type=Path)
    source.add_argument("--database", type=Path)
    parser.add_argument("--instance-id")
    subcommands = parser.add_subparsers(dest="command", required=True)
    recovery = subcommands.add_parser("recovery")
    approval = recovery.add_subparsers(dest="operation", required=True).add_parser("approve")
    approval.add_argument("request_id")
    snapshots = subcommands.add_parser("snapshot")
    snapshots.add_argument("--timeout", type=float, default=30)
    operations = snapshots.add_subparsers(dest="operation", required=True)
    for operation in ("create", "inspect"):
        operations.add_parser(operation).add_argument("location", type=Path)
    restoration = subcommands.add_parser("restore")
    restoration.add_argument("--timeout", type=float, default=30)
    restore_operations = restoration.add_subparsers(dest="operation", required=True)
    prepare = restore_operations.add_parser("prepare")
    prepare.add_argument("snapshot", type=Path)
    prepare.add_argument("location", type=Path)
    for operation in ("inspect", "activate"):
        restore_operations.add_parser(operation).add_argument("location", type=Path)
    for operation in ("resume", "status"):
        restore_operations.add_parser(operation).add_argument("restore_id")
    args = parser.parse_args(argv)
    incoming = sys.stdin if input_stream is None else input_stream
    outgoing = sys.stdout if output_stream is None else output_stream
    errors = sys.stderr if error_stream is None else error_stream
    owned: OwnedStorage | None = None
    try:
        if args.command == "restore":
            return restore(args, outgoing, SystemClock())
        if args.command == "snapshot" and args.operation == "inspect":
            if (
                args.data_directory is not None
                or args.database is not None
                or args.instance_id is None
            ):
                raise InvalidInput("invalid_persistent_configuration")
            return _snapshot(args, None, Installation(args.instance_id, args.channel), outgoing)
        if args.data_directory is not None:
            if args.instance_id is not None:
                raise InvalidInput("invalid_persistent_configuration")
            owned = attach_storage(args.data_directory, args.channel)
            database, installation = owned.database, owned.installation
        else:
            if args.database is None or args.instance_id is None:
                raise InvalidInput("invalid_persistent_configuration")
            installation = Installation(args.instance_id, args.channel)
            database = attach_database(args.database, installation)
        if args.command == "snapshot":
            return _snapshot(args, database, installation, outgoing)
        commands = RecoveryConsole(
            database,
            installation,
            SystemClock(),
            SecureIdentifiers(),
            TerminalRecoveryConfirmation(incoming, outgoing),
        )
        receipt = commands.approve(args.request_id)
        outgoing.write(
            json.dumps(
                {
                    "state": "historical" if receipt.historical else "committed",
                    "archived_by": receipt.archived_by,
                    "operation_id": receipt.operation_id,
                    "result": receipt.result.decode(),
                    "message": (
                        "This approval is historical and has no effect in current state."
                        if receipt.historical
                        else "Console approval was saved. The same target must freshly prove "
                        "HA administrator status to finish."
                    ),
                },
                ensure_ascii=True,
            )
            + "\n"
        )
        outgoing.flush()
        return 0
    except DomusError:
        errors.write(
            "Domus could not complete or confirm the console operation. Inspect the same recovery "
            "request, snapshot candidate or activation before retrying. "
            "Existing records are retained.\n"
        )
        return 2
    except OSError:
        errors.write(
            "Domus could not confirm the command result. Inspect the same request or candidate; "
            "do not replace existing data. Existing records are retained.\n"
        )
        return 1
    except KeyboardInterrupt:
        errors.write(
            "Console operation was interrupted. "
            "Inspect the same request or candidate before retrying.\n"
        )
        return 130
    finally:
        if owned is not None:
            owned.close()


if __name__ == "__main__":
    raise SystemExit(main())
