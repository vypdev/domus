"""A source is bound to the verified server subject and returns no credential or authority."""

from typing import Protocol

from domus.domain.member_sources import MemberSourceSnapshot


class MemberProfileSource(Protocol):
    def read(self) -> MemberSourceSnapshot: ...
