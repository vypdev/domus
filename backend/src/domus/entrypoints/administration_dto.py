"""Closed profile wire values; owner identity is deliberately absent from preference inputs."""

from typing import Literal

from pydantic import Field

from domus.domain.member_profiles import MemberLocale
from domus.entrypoints.household_http import ReceiptResponse
from domus.entrypoints.http_contract import StrictModel

type AdministrationAction = Literal[
    "household.update",
    "member.update",
    "policy.update",
    "member.presentation.update",
    "member.preferences.update",
]


class AliasRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)
    alias: str | None


class PreferencesRequest(StrictModel):
    expected_revision: int = Field(ge=1, le=2**63 - 1)
    locale: MemberLocale | None = Field(strict=False)
    routine_participation_summaries: bool


class PresentationResponse(StrictModel):
    member_id: str
    alias: str | None
    revision: int = Field(ge=1, le=2**63 - 1)


class PreferencesResponse(StrictModel):
    member_id: str
    locale: MemberLocale | None = Field(strict=False)
    routine_participation_summaries: bool
    revision: int = Field(ge=1, le=2**63 - 1)
    notification_delivery: Literal["unavailable"] = "unavailable"


class AdministrationReceipt(ReceiptResponse):
    notification_delivery: Literal["unavailable"] = "unavailable"


class AdministrationOperation(AdministrationReceipt):
    action: AdministrationAction
    command_key: str
    event_delivery: Literal["pending", "delivered", "suppressed"]


class AdministrationJournal(StrictModel):
    namespace: Literal["administration"] = "administration"
    version: Literal[1] = 1
    maximum_records: Literal[8] = 8
    maximum_bytes: Literal[65536] = 65536
    lifetime_ms: Literal[3600000] = 3600000


class AdministrationCapabilities(StrictModel):
    state: Literal["available"] = "available"
    contract_version: Literal[1] = 1
    exact_revisions: Literal["json-integer-int64"] = "json-integer-int64"
    actions: tuple[AdministrationAction, ...]
    journal: AdministrationJournal = Field(default_factory=AdministrationJournal)
