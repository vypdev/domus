"""Task mutation facts are shared by interactive and delegated command entrypoints."""

from domus.application.commands import Change
from domus.application.task_requests import TaskRequest
from domus.domain.storage import JsonDocument


def task_change(transition: str, request: TaskRequest, result: JsonDocument) -> Change:
    detail = JsonDocument.from_value(
        {
            "transition": transition,
            "request": request.document().decode(),
            "result": result.decode(),
        }
    )
    event = JsonDocument.from_value({"version": 1, "kind": transition, **result.decode()})
    return Change(result, detail, event)
