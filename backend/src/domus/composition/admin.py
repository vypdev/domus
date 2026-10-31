"""Installation-console composition can approve recovery; it cannot complete human proof."""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from domus.application.recovery_commands import RecoveryConsole
from domus.domain.errors import DomusError, InvalidInput
from domus.domain.storage import Installation
from domus.entrypoints.console_recovery import TerminalRecoveryConfirmation
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.owned_storage import OwnedStorage, attach_database, attach_storage


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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data-directory", type=Path)
    source.add_argument("--database", type=Path)
    parser.add_argument("--instance-id")
    recovery = parser.add_subparsers(dest="command", required=True).add_parser("recovery")
    approval = recovery.add_subparsers(dest="operation", required=True).add_parser("approve")
    approval.add_argument("request_id")
    args = parser.parse_args(argv)
    incoming = sys.stdin if input_stream is None else input_stream
    outgoing = sys.stdout if output_stream is None else output_stream
    errors = sys.stderr if error_stream is None else error_stream
    owned: OwnedStorage | None = None
    try:
        if args.data_directory is not None:
            if args.instance_id is not None:
                raise InvalidInput("invalid_persistent_configuration")
            owned = attach_storage(args.data_directory, args.channel)
            database, installation = owned.database, owned.installation
        else:
            if args.instance_id is None:
                raise InvalidInput("invalid_persistent_configuration")
            installation = Installation(args.instance_id, args.channel)
            database = attach_database(args.database, installation)
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
                    "state": "committed",
                    "operation_id": receipt.operation_id,
                    "result": receipt.result.decode(),
                    "message": (
                        "Console approval was saved. The same target must freshly prove "
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
            "Domus could not complete or confirm approval. Review the same recovery request; "
            "retrying approval for that request is safe. Existing records are retained.\n"
        )
        return 2
    except OSError:
        errors.write(
            "Domus could not confirm the command result. Inspect or retry the same request; "
            "do not create a replacement. Existing records are retained.\n"
        )
        return 1
    except KeyboardInterrupt:
        errors.write(
            "Console confirmation was interrupted. Review the same request before retrying.\n"
        )
        return 130
    finally:
        if owned is not None:
            owned.close()


if __name__ == "__main__":
    raise SystemExit(main())
