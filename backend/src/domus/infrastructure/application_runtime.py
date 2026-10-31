"""System UTC, collision-resistant record identifiers and IANA timezone validation."""

import secrets
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domus.domain.errors import InvalidInput


class SystemClock:
    def now(self) -> int:
        return time.time_ns() // 1_000_000


class SecureIdentifiers:
    def new(self) -> str:
        return "domus_" + secrets.token_urlsafe(24)


class TimeZoneCatalog:
    def require(self, time_zone: str) -> None:
        try:
            ZoneInfo(time_zone)
        except ZoneInfoNotFoundError, ValueError, TypeError, UnicodeError:
            raise InvalidInput("invalid_time_zone") from None
