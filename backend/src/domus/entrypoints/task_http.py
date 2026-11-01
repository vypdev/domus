"""Task routes adapt strict wire contracts to shared application commands and bounded queries."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.params import Depends

from domus.application.task_commands import TaskCommands
from domus.application.task_queries import (
    DefinitionSummary,
    OccurrenceSummary,
    TaskHistoryItem,
    TaskMaterialsView,
    TaskPage,
    TaskPolicyView,
    TaskQueries,
)
from domus.application.task_requests import (
    AssignTask,
    ClaimTask,
    CompleteTask,
    CreateTask,
    CreateTaskOccurrence,
    ReopenTask,
    TransitionTask,
    UpdateTaskDefinition,
    UpdateTaskDependencies,
    UpdateTaskPolicy,
    VerifyTask,
)
from domus.domain.task_values import DefinitionState
from domus.entrypoints.household_http import (
    OperationResponse,
    ReceiptResponse,
    _EmptyQuery,
    _JSONRoute,
    _key,
    _receipt,
)
from domus.entrypoints.task_dto import (
    AssignmentBody,
    CompleteBody,
    CreateDefinitionBody,
    CreateOccurrenceBody,
    DefinitionsQuery,
    DependenciesBody,
    Identifier,
    MaterialsQuery,
    OccurrenceBody,
    OccurrencesQuery,
    PageQuery,
    PolicyBody,
    ReopenBody,
    TransitionBody,
    UpdateDefinitionBody,
    VerifyBody,
)
from domus.entrypoints.task_response import (
    TaskDefinition,
    TaskDetail,
    definition_response,
    detail_response,
)


@dataclass(frozen=True, slots=True)
class TaskHTTPContext:
    queries: Callable[[], TaskQueries]
    commands: TaskCommands


def create_task_router(
    context: Callable[[Request], TaskHTTPContext], *, security: Depends
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/tasks", dependencies=[security], route_class=_JSONRoute)
    write_contract = {
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        ]
    }

    @router.get("/policy", response_model=TaskPolicyView)
    def policy(request: Request, query: Annotated[_EmptyQuery, Query()]) -> TaskPolicyView:
        return context(request).queries().policy()

    @router.put("/policy", response_model=ReceiptResponse, openapi_extra=write_contract)
    def update_policy(
        request: Request, body: PolicyBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.update_policy(
                _key(request), UpdateTaskPolicy(body.expected_revision, body.rules.domain())
            )
        )

    @router.get("/definitions", response_model=TaskPage[DefinitionSummary])
    def definitions(
        request: Request, query: Annotated[DefinitionsQuery, Query()]
    ) -> TaskPage[DefinitionSummary]:
        return (
            context(request)
            .queries()
            .definitions(limit=query.limit, cursor=query.cursor, state=query.state)
        )

    @router.post("/definitions", response_model=ReceiptResponse, openapi_extra=write_contract)
    def create(
        request: Request, body: CreateDefinitionBody, query: Annotated[_EmptyQuery, Query()]
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.create(
                _key(request),
                CreateTask(
                    body.content(),
                    body.overrides.domain(),
                    DefinitionState(body.state),
                    body.expected_revision,
                    body.selections(),
                ),
            )
        )

    @router.get("/definitions/{definition_id}", response_model=TaskDefinition)
    def definition(
        definition_id: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> TaskDefinition:
        return definition_response(context(request).queries().definition(definition_id))

    @router.put(
        "/definitions/{definition_id}", response_model=ReceiptResponse, openapi_extra=write_contract
    )
    def update_definition(
        definition_id: Identifier,
        request: Request,
        body: UpdateDefinitionBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.update_definition(
                _key(request),
                UpdateTaskDefinition(
                    definition_id,
                    body.expected_revision,
                    body.content(),
                    body.state,
                    None if body.overrides is None else body.overrides.domain(),
                    body.selections(),
                ),
            )
        )

    @router.post(
        "/definitions/{definition_id}/occurrences",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def create_occurrence(
        definition_id: Identifier,
        request: Request,
        body: CreateOccurrenceBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.create_occurrence(
                _key(request),
                CreateTaskOccurrence(
                    definition_id,
                    body.expected_revision,
                    tuple(body.assignee_ids),
                    tuple(body.prerequisite_ids),
                    tuple(body.required_subtask_ids),
                    body.due_at,
                ),
            )
        )

    @router.get("/occurrences", response_model=TaskPage[OccurrenceSummary])
    def occurrences(
        request: Request, query: Annotated[OccurrencesQuery, Query()]
    ) -> TaskPage[OccurrenceSummary]:
        return (
            context(request)
            .queries()
            .occurrences(
                limit=query.limit,
                cursor=query.cursor,
                state=query.state,
                definition_id=query.definition_id,
                assignee_id=query.assignee_id,
            )
        )

    @router.get("/occurrences/{occurrence_id}", response_model=TaskDetail)
    def occurrence(
        occurrence_id: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> TaskDetail:
        return detail_response(context(request).queries().occurrence(occurrence_id))

    @router.put(
        "/occurrences/{occurrence_id}/assignment",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def assign(
        occurrence_id: Identifier,
        request: Request,
        body: AssignmentBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.assign(
                _key(request),
                AssignTask(occurrence_id, body.expected_revision, tuple(body.assignee_ids)),
            )
        )

    @router.put(
        "/occurrences/{occurrence_id}/dependencies",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def dependencies(
        occurrence_id: Identifier,
        request: Request,
        body: DependenciesBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.update_dependencies(
                _key(request),
                UpdateTaskDependencies(
                    occurrence_id,
                    body.expected_revision,
                    tuple(body.prerequisite_ids),
                    tuple(body.required_subtask_ids),
                ),
            )
        )

    @router.post(
        "/occurrences/{occurrence_id}/claim",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def claim(
        occurrence_id: Identifier,
        request: Request,
        body: OccurrenceBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.claim(
                _key(request), ClaimTask(occurrence_id, body.expected_revision)
            )
        )

    @router.post(
        "/occurrences/{occurrence_id}/transition",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def transition(
        occurrence_id: Identifier,
        request: Request,
        body: TransitionBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.transition(
                _key(request),
                TransitionTask(occurrence_id, body.expected_revision, body.target, body.reason),
            )
        )

    @router.post(
        "/occurrences/{occurrence_id}/complete",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def complete(
        occurrence_id: Identifier,
        request: Request,
        body: CompleteBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.complete(
                _key(request),
                CompleteTask(
                    occurrence_id,
                    body.expected_revision,
                    tuple(body.performer_ids),
                    body.performed_at,
                    body.usages(),
                ),
            )
        )

    @router.post(
        "/occurrences/{occurrence_id}/verify",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def verify(
        occurrence_id: Identifier,
        request: Request,
        body: VerifyBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.verify(
                _key(request),
                VerifyTask(
                    occurrence_id, body.expected_revision, body.cycle_id, body.decision, body.reason
                ),
            )
        )

    @router.post(
        "/occurrences/{occurrence_id}/reopen",
        response_model=ReceiptResponse,
        openapi_extra=write_contract,
    )
    def reopen(
        occurrence_id: Identifier,
        request: Request,
        body: ReopenBody,
        query: Annotated[_EmptyQuery, Query()],
    ) -> ReceiptResponse:
        return _receipt(
            context(request).commands.reopen(
                _key(request),
                ReopenTask(occurrence_id, body.expected_revision, body.cycle_id, body.reason),
            )
        )

    @router.get("/occurrences/{occurrence_id}/materials", response_model=TaskMaterialsView)
    def materials(
        occurrence_id: Identifier, request: Request, query: Annotated[MaterialsQuery, Query()]
    ) -> TaskMaterialsView:
        return context(request).queries().materials(occurrence_id, query.cycle_id)

    @router.get("/occurrences/{occurrence_id}/history", response_model=TaskPage[TaskHistoryItem])
    def history(
        occurrence_id: Identifier, request: Request, query: Annotated[PageQuery, Query()]
    ) -> TaskPage[TaskHistoryItem]:
        return (
            context(request)
            .queries()
            .history(occurrence_id, limit=query.limit, cursor=query.cursor)
        )

    @router.get("/operations/{operation_id}", response_model=OperationResponse)
    def operation(
        operation_id: Identifier, request: Request, query: Annotated[_EmptyQuery, Query()]
    ) -> OperationResponse:
        view = context(request).queries().operation(operation_id)
        return OperationResponse(
            **_receipt(view.receipt).model_dump(),
            delivery="suppressed"
            if view.receipt.historical
            else "delivered"
            if view.delivered
            else "pending",
        )

    return router
