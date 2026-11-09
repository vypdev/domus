"""The durable choice between the two appearances of a repeated local time."""

from enum import StrEnum


class FoldPolicy(StrEnum):
    FIRST = "first_instant"
    SECOND = "second_instant"
