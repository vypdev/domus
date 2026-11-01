"""Recurrence application code receives temporal facts, never provider timezone objects."""

from typing import Protocol

from domus.domain.recurrence_time import NominalTime, RelativeInterval, ResolvedTime, TimePolicy


class RecurrenceTimes(Protocol):
    @property
    def data_identity(self) -> str: ...

    def resolve(self, nominal: NominalTime, policy: TimePolicy) -> ResolvedTime: ...

    def after_local_days(
        self, performed_at: int, interval: RelativeInterval, policy: TimePolicy
    ) -> ResolvedTime: ...
