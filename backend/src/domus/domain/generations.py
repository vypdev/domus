"""A path-free versioned identity selects exactly one ready installation generation."""

from dataclasses import dataclass
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation, JsonDocument, validate_identifier


@dataclass(frozen=True, slots=True)
class GenerationSelection:
    installation: Installation
    generation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.installation, Installation):
            raise InvalidInput("invalid_generation_selection")
        validate_identifier(self.generation_id)

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "schema_version": 2,
                "instance_id": self.installation.instance_id,
                "channel": self.installation.channel,
                "state": "ready",
                "generation_id": self.generation_id,
            }
        )

    @classmethod
    def from_value(cls, value: object) -> GenerationSelection:
        if type(value) is not dict:
            raise InvalidInput("invalid_generation_selection")
        data = cast(dict[str, object], value)
        if (
            set(data) != {"schema_version", "instance_id", "channel", "state", "generation_id"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 2
            or data["state"] != "ready"
        ):
            raise InvalidInput("invalid_generation_selection")
        return cls(
            Installation(cast(str, data["instance_id"]), cast(str, data["channel"])),
            cast(str, data["generation_id"]),
        )
