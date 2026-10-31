"""A real terminal displays the exact recovery binding before accepting explicit approval."""

import json
from dataclasses import dataclass
from typing import TextIO

from domus.domain.errors import Forbidden
from domus.domain.identity import Member
from domus.domain.recovery import RecoveryRequest


@dataclass
class TerminalRecoveryConfirmation:
    incoming: TextIO
    outgoing: TextIO

    def confirm(self, request: RecoveryRequest, member: Member | None) -> bool:
        if not self.incoming.isatty() or not self.outgoing.isatty():
            raise Forbidden("console_tty_required")
        details = request.document().decode()
        details["previous_role"] = member.role.value if member is not None else None
        details["previous_status"] = member.status.value if member is not None else None
        details["grant"] = (
            "Explicit Domus administrator; active membership. "
            "Existing linkage and exceptions are retained."
        )
        self.outgoing.write("Review the exact recovery target and installation:\n")
        self.outgoing.write(json.dumps(details, ensure_ascii=True, indent=2) + "\n")
        challenge = f"APPROVE {request.request_id} {request.target_ha_user_id}"
        self.outgoing.write("To approve this target, type exactly: " + challenge + "\n> ")
        self.outgoing.flush()
        return self.incoming.readline(1024).rstrip("\r\n") == challenge
