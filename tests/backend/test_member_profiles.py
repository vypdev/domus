"""Public aliases and private preferences cannot replace canonical member authority."""

from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from domus.domain.errors import InvalidInput
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation


def test_default_records_do_not_invent_ha_metadata_or_identity_grants() -> None:
    presentation = MemberPresentation("member_1", "home")
    preferences = MemberPreferences("member_1", "home")
    assert presentation.alias is None
    assert preferences.locale is None
    assert preferences.routine_participation_summaries is True
    assert presentation.revision == preferences.revision == 1
    assert not {"ha_user_id", "role", "status", "display_name", "avatar_reference"} & set(
        asdict(presentation)
    )
    assert not {"locale", "routine_participation_summaries"} & set(asdict(presentation))


@pytest.mark.parametrize(
    "alias,expected",
    [
        (None, None),
        ("A", "A"),
        ("  Nuria  ", "Nuria"),
        ("\u00a0Álex\u00a0", "Álex"),
        ("🧹" * 80, "🧹" * 80),
        ("e\u0301", "e\u0301"),
        ("<img src=x onerror=alert(1)>", "<img src=x onerror=alert(1)>"),
        ("javascript:alert(1)", "javascript:alert(1)"),
    ],
)
def test_alias_is_nullable_trimmed_codepoint_bounded_and_keeps_literal_text(
    alias: str | None, expected: str | None
) -> None:
    assert MemberPresentation("member_1", "home", alias).alias == expected


@pytest.mark.parametrize("codepoint", [*range(32), *range(127, 160)])
def test_every_unicode_cc_control_is_rejected_before_whitespace_normalization(
    codepoint: int,
) -> None:
    alias = chr(codepoint) + "Private alias" + chr(codepoint)
    with pytest.raises(InvalidInput, match="^invalid_member_alias$"):
        MemberPresentation("member_1", "home", alias)


@pytest.mark.parametrize(
    "alias", ["", " ", "\u00a0", "a" * 81, "🧹" * 81, True, 1, [], "\ud800", "a\udfff"]
)
def test_invalid_alias_never_becomes_a_saved_value_or_error_detail(alias: object) -> None:
    with pytest.raises(InvalidInput, match="^invalid_member_alias$") as error:
        MemberPresentation("member_1", "home", alias)
    assert str(error.value) == "invalid_member_alias"


def test_alias_clear_preserves_record_scope_and_cannot_modify_private_preferences() -> None:
    private = MemberPreferences("member_1", "home", MemberLocale.SPANISH, False, 9)
    public = MemberPresentation("member_1", "home", "Domus alias", 4)
    cleared = replace(public, alias=None, revision=5)
    assert (cleared.member_id, cleared.household_id, cleared.alias) == ("member_1", "home", None)
    assert public.alias == "Domus alias"
    assert (private.locale, private.routine_participation_summaries, private.revision) == (
        MemberLocale.SPANISH,
        False,
        9,
    )


@pytest.mark.parametrize("locale", [None, *MemberLocale])
@pytest.mark.parametrize("summaries", [False, True])
def test_own_preferences_preserve_explicit_values_and_browser_following(
    locale: MemberLocale | None, summaries: bool
) -> None:
    preferences = MemberPreferences("member_1", "home", locale, summaries)
    assert preferences.locale is locale
    assert preferences.routine_participation_summaries is summaries
    assert {item.value for item in MemberLocale} == {"en", "es"}


@pytest.mark.parametrize("locale", ["en", "es", "fr", "", True, 1, []])
def test_domain_preferences_require_the_closed_locale_enum(locale: object) -> None:
    with pytest.raises(InvalidInput, match="^invalid_member_preferences$"):
        MemberPreferences("member_1", "home", locale)


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_summary_preference_requires_an_exact_boolean(value: object) -> None:
    with pytest.raises(InvalidInput, match="^invalid_member_preferences$"):
        MemberPreferences("member_1", "home", routine_participation_summaries=value)


@pytest.mark.parametrize("model", [MemberPresentation, MemberPreferences])
@pytest.mark.parametrize("field", ["member_id", "household_id"])
@pytest.mark.parametrize("value", [None, True, "", "bad id", "x" * 129])
def test_public_and_private_records_require_valid_scoped_identifiers(
    model: type, field: str, value: object
) -> None:
    values = {"member_id": "member_1", "household_id": "home", field: value}
    with pytest.raises(InvalidInput, match="^invalid_identifier$"):
        model(**values)


@pytest.mark.parametrize("model", [MemberPresentation, MemberPreferences])
@pytest.mark.parametrize("revision", [True, None, 0, -1, 1.5, 2**63])
def test_profile_records_require_a_positive_bounded_integer_revision(
    model: type, revision: object
) -> None:
    with pytest.raises(InvalidInput, match="^invalid_revision$"):
        model("member_1", "home", revision=revision)


@pytest.mark.parametrize("model", [MemberPresentation, MemberPreferences])
def test_records_are_immutable_and_accept_the_last_supported_revision(model: type) -> None:
    record = model("member_1", "home", revision=2**63 - 1)
    assert record.revision == 2**63 - 1
    with pytest.raises(FrozenInstanceError):
        record.revision = 1
