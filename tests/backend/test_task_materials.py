"""Material facts retain original submission and require scoped real-consumer proof."""

from dataclasses import replace

import pytest
from test_task_material_values import line

from domus.application.task_material_ports import InventoryMaterialResult, MaterialPostingRequest
from domus.application.task_materials import TaskMaterials
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.task_material_values import MaterialAction, MaterialSelection
from domus.domain.task_material_values import MaterialPendingReason as Pending
from domus.domain.task_material_values import MaterialQuantity as Quantity
from domus.domain.task_material_values import MaterialState as State
from domus.domain.task_materials import MaterialIntent, MaterialPosting
from domus.domain.task_values import MaterialRecording


def intent(quantity="2", *, authorized=True, mode=MaterialRecording.REVIEW_ON_COMPLETION):
    return MaterialIntent.record(
        "intent",
        "home",
        "occurrence",
        "cycle",
        line(),
        None if quantity is None else Quantity(quantity),
        recorded_by="recorder",
        performed_at=90,
        recorded_at=100,
        recording_mode=mode,
        authorized=authorized,
    )


def posting(value, **changes):
    result = MaterialPosting(
        value.intent_id,
        value.household_id,
        value.occurrence_id,
        value.cycle_id,
        value.line.line_id,
        value.line.binding.reference_id,
        value.line.binding.revision,
        value.revision,
        value.effect_revision,
        value.quantity,
        f"inventory-operation-{value.effect_revision}",
        f"movement-{value.effect_revision}",
        101,
    )
    return replace(result, **changes)


@pytest.mark.parametrize(
    "quantity,authorized,mode,state,reason,needs_posting",
    [
        (
            None,
            True,
            MaterialRecording.REVIEW_ON_COMPLETION,
            State.PENDING_RECORDING,
            Pending.ACTUAL_QUANTITY_REQUIRED,
            False,
        ),
        ("0", False, MaterialRecording.REVIEW_ON_COMPLETION, State.NOT_USED, None, False),
        (
            "1",
            False,
            MaterialRecording.REVIEW_ON_COMPLETION,
            State.PENDING_AUTHORIZATION,
            Pending.PERMISSION_REQUIRED,
            True,
        ),
        (
            "1",
            True,
            MaterialRecording.SEPARATE,
            State.PENDING_PROCESSING,
            Pending.EXPLICIT_SETTLEMENT_REQUIRED,
            True,
        ),
        (
            "1",
            True,
            MaterialRecording.REVIEW_ON_COMPLETION,
            State.PENDING_PROCESSING,
            Pending.AWAITING_INVENTORY,
            True,
        ),
    ],
)
def test_recording_distinguishes_unknown_zero_denied_and_explicit_confirmation(
    quantity, authorized, mode, state, reason, needs_posting
):
    value = intent(quantity, authorized=authorized, mode=mode)
    assert (
        value.state is state
        and value.pending_reason is reason
        and value.needs_posting is needs_posting
    )
    assert value.submitted_quantity == value.quantity and value.posting is None
    assert value.revision == value.effect_revision == 1
    assert value.performed_at == 90 and value.created_at == value.updated_at == 100


@pytest.mark.parametrize(
    "reason,state",
    [
        (Pending.PERMISSION_REQUIRED, State.PENDING_AUTHORIZATION),
        (Pending.STOCK_SHORTAGE, State.PENDING_REGULARIZATION),
        (Pending.BINDING_CHANGED, State.PENDING_REGULARIZATION),
        (Pending.INVENTORY_UNAVAILABLE, State.PENDING_PROCESSING),
        (Pending.EXPLICIT_SETTLEMENT_REQUIRED, State.PENDING_PROCESSING),
    ],
)
def test_pending_facts_never_claim_posting_or_change_effect_identity(reason, state):
    original = intent()
    held = original.defer(reason, 110)
    assert held.state is state and held.revision == 2 and held.effect_revision == 1
    assert held.submitted_quantity == original.quantity and held.posting is None
    assert held.defer(reason, 120) is held
    with pytest.raises(InvalidInput):
        held.defer(reason, 109)


def test_only_actual_matching_inventory_confirmation_makes_usage_posted():
    original = intent()
    proof = posting(original)
    confirmed = original.confirm(proof, 110)
    assert confirmed.state is State.POSTED and not confirmed.needs_posting
    assert confirmed.posting == proof and confirmed.revision == 2 and confirmed.effect_revision == 1
    assert confirmed.confirm(proof, 120) is confirmed
    with pytest.raises(Conflict):
        confirmed.confirm(replace(proof, movement_id="other"), 120)
    with pytest.raises(Conflict):
        confirmed.defer(Pending.STOCK_SHORTAGE, 120)
    with pytest.raises(Conflict):
        confirmed.dismiss("Cannot erase real stock", 120)


def test_a_late_exact_effect_confirmation_can_reconcile_pending_metadata_without_rewriting_time():
    original = intent()
    proof = posting(original)
    pending = original.defer(Pending.INVENTORY_UNAVAILABLE, 120)
    confirmed = pending.confirm(proof, 130)
    assert confirmed.posting.posted_at == 101 and confirmed.updated_at == 130
    assert confirmed.state is State.POSTED and confirmed.effect_revision == 1


def test_correction_preserves_original_submission_and_previous_confirmed_effect_until_confirmed():
    original = intent().confirm(posting(intent()), 110)
    corrected = original.correct(Quantity("3"), "Actual quantity was higher", 120)
    assert corrected.state is State.PENDING_PROCESSING and corrected.needs_posting
    assert corrected.quantity == Quantity("3") and corrected.submitted_quantity == Quantity("2")
    assert (
        corrected.posting == original.posting
        and corrected.revision == 3
        and corrected.effect_revision == 2
    )
    held = corrected.defer(Pending.STOCK_SHORTAGE, 130)
    assert held.posting == original.posting and held.quantity == Quantity("3")
    proof = posting(
        held,
        posted_at=140,
        inventory_operation_id="correction-operation",
        movement_id="actual-adjustment",
    )
    result = held.confirm(proof, 150)
    assert result.state is State.CORRECTED and result.submitted_quantity == Quantity("2")
    assert result.posting.quantity == Quantity("3") and result.effect_revision == 2
    with pytest.raises(Conflict):
        result.confirm(original.posting, 160)


def test_zero_after_posting_still_needs_inventory_correction_and_never_fabricates_a_return():
    posted = intent().confirm(posting(intent()), 110)
    corrected = posted.correct(Quantity("0"), "Nothing was actually used", 120)
    assert corrected.needs_posting and corrected.posting == posted.posting
    assert corrected.quantity.is_zero and corrected.state is State.PENDING_PROCESSING
    proof = posting(corrected, posted_at=130)
    final = corrected.confirm(proof, 140)
    assert final.state is State.CORRECTED and final.posting.quantity.is_zero


def test_reverting_a_pending_correction_to_confirmed_quantity_needs_no_new_movement():
    posted = intent().confirm(posting(intent()), 110)
    pending = posted.correct(Quantity("4"), "Review usage", 120)
    reverted = pending.correct(Quantity("2"), "Original confirmed amount was right", 130)
    assert reverted.state is State.CORRECTED and not reverted.needs_posting
    assert reverted.posting == posted.posting and reverted.effect_revision == 3


def test_missing_or_zero_actuals_can_be_explicitly_corrected_without_erasing_source():
    unknown = intent(None).correct(Quantity("0"), "Confirmed none used", 110)
    assert unknown.state is State.NOT_USED and unknown.submitted_quantity is None
    positive = unknown.correct(Quantity("1"), "Actual use confirmed", 120)
    assert positive.needs_posting and positive.submitted_quantity is None
    assert positive.effect_revision == 3
    with pytest.raises(Conflict):
        positive.correct(Quantity("1"), "Unchanged", 130)
    with pytest.raises(InvalidInput):
        positive.correct(Quantity("2"), " ", 130)


def test_dismissal_retains_source_without_inventory_effect_and_is_terminal():
    original = intent(None)
    dismissed = original.dismiss("Recording is not applicable", 110)
    assert dismissed.state is State.DISMISSED and dismissed.submitted_quantity is None
    assert not dismissed.needs_posting and dismissed.posting is None
    with pytest.raises(Conflict):
        dismissed.dismiss("Again", 120)
    with pytest.raises(Conflict):
        dismissed.correct(Quantity("2"), "Change", 120)
    with pytest.raises(InvalidInput):
        original.dismiss(" ", 110)
    with pytest.raises(Conflict):
        intent("0").dismiss("Already not used", 110)


@pytest.mark.parametrize(
    "changes",
    [
        {"intent_id": "other"},
        {"household_id": "other"},
        {"occurrence_id": "other"},
        {"cycle_id": "old"},
        {"line_id": "other"},
        {"reference_id": "other"},
        {"binding_revision": 2},
    ],
)
def test_foreign_confirmation_never_crosses_scope(changes):
    original = intent()
    with pytest.raises(InvalidInput, match="invalid_material_confirmation"):
        original.confirm(posting(original, **changes), 110)


@pytest.mark.parametrize(
    "changes", [{"quantity": Quantity("3")}, {"intent_revision": 2}, {"effect_revision": 2}]
)
def test_stale_or_future_effect_confirmation_cannot_become_current(changes):
    original = intent()
    with pytest.raises(Conflict):
        original.confirm(posting(original, **changes), 110)


@pytest.mark.parametrize("changes", [{"posted_at": 99}, {"posted_at": 111}])
def test_confirmation_time_must_belong_to_recorded_work_and_not_the_future(changes):
    original = intent()
    with pytest.raises(InvalidInput):
        original.confirm(posting(original, **changes), 110)


@pytest.mark.parametrize(
    "changes",
    [
        {"intent_id": "bad id"},
        {"binding_revision": True},
        {"effect_revision": 0},
        {"quantity": "1"},
        {"posted_at": True},
        {"movement_id": ""},
    ],
)
def test_confirmation_values_are_strict_even_before_scope_matching(changes):
    with pytest.raises(InvalidInput):
        posting(intent(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"authorized_at_recording": 1},
        {"recording_mode": "separate_recording"},
        {"state": "posted"},
        {"line": None},
        {"household_id": "other"},
        {"quantity": "2"},
        {"submitted_quantity": "2"},
        {"performed_at": 101},
        {"updated_at": 99},
        {"effect_revision": 2},
        {"quantity": Quantity("3")},
        {"pending_reason": None},
        {"pending_reason": Pending.ACTUAL_QUANTITY_REQUIRED},
        {"reason": "Unrecorded correction"},
        {"state": State.POSTED},
        {"state": State.NOT_USED},
        {"state": State.DISMISSED},
    ],
)
def test_inconsistent_intent_records_fail_closed(changes):
    with pytest.raises(InvalidInput):
        replace(intent(), **changes)


def test_material_revision_exhaustion_and_invalid_transition_inputs_are_inert():
    exhausted = replace(intent(), revision=2**63 - 1)
    for change in (
        lambda: exhausted.defer(Pending.STOCK_SHORTAGE, 110),
        lambda: exhausted.correct(Quantity("3"), "Correct", 110),
        lambda: exhausted.dismiss("Dismiss", 110),
        lambda: exhausted.confirm(posting(exhausted), 110),
    ):
        with pytest.raises(Conflict, match="task_revision_exhausted"):
            change()
    for change in (
        lambda: intent().defer("insufficient_stock", 110),
        lambda: intent().defer(Pending.ACTUAL_QUANTITY_REQUIRED, 110),
        lambda: intent("0").defer(Pending.STOCK_SHORTAGE, 110),
        lambda: intent().confirm(None, 110),
        lambda: intent().correct("3", "Correct", 110),
    ):
        with pytest.raises((InvalidInput, Conflict)):
            change()


class Clock:
    value = 110

    def now(self):
        return self.value


class IDs:
    count = 0

    def new(self):
        self.count += 1
        return "generated-line-" + str(self.count)


class Authority:
    """Explicit current-authority port fake, not HA proof or a permission implementation."""

    denied = False
    member_id = "operator"

    def __init__(self):
        self.calls = []

    def link_actor(self, household_id):
        self.calls.append((household_id, "link"))
        if self.denied:
            raise Forbidden("permission_denied")
        return self.member_id

    def require(self, value, action):
        self.calls.append((value.intent_id, action))
        if self.denied:
            raise Forbidden("permission_denied")
        return self.member_id


class Inventory:
    """Semantic fake certifies test-only results; it is not an Inventory ledger."""

    def __init__(self):
        self.calls = []
        self.binding = line().binding
        self.result = "success"

    def resolve(self, household_id, actor_member_id, reference_id):
        self.calls.append(("resolve", household_id, actor_member_id, reference_id))
        if isinstance(self.binding, Exception):
            raise self.binding
        return self.binding

    def settle(self, request):
        self.calls.append(("settle", request))
        if isinstance(self.result, Exception):
            raise self.result
        if self.result == "success":
            return InventoryMaterialResult(posting=posting(request.intent, posted_at=110))
        return self.result


def processor():
    inventory, authority, clock, ids = Inventory(), Authority(), Clock(), IDs()
    return TaskMaterials(inventory, authority, clock, ids), inventory, authority, clock, ids


def test_source_effect_key_survives_pending_retries_and_actor_changes_but_not_quantity_correction():
    original = intent()
    key = MaterialPostingRequest(original, "first").source_key
    assert len(key) <= 128 and key.startswith("task-material:")
    assert (
        MaterialPostingRequest(original.defer(Pending.STOCK_SHORTAGE, 110), "second").source_key
        == key
    )
    assert (
        MaterialPostingRequest(original.correct(Quantity("3"), "Actual", 110), "first").source_key
        != key
    )
    for invalid in (
        lambda: MaterialPostingRequest(None, "member"),
        lambda: MaterialPostingRequest(original, "bad id"),
        lambda: MaterialPostingRequest(intent("0"), "member"),
    ):
        with pytest.raises(InvalidInput):
            invalid()


@pytest.mark.parametrize(
    "posting_value,pending",
    [
        (None, None),
        (None, "inventory_unavailable"),
        (None, Pending.ACTUAL_QUANTITY_REQUIRED),
        (None, Pending.EXPLICIT_SETTLEMENT_REQUIRED),
        (posting(intent()), Pending.STOCK_SHORTAGE),
        ("not-a-posting", None),
    ],
)
def test_inventory_result_contract_cannot_claim_ambiguous_or_task_owned_outcomes(
    posting_value, pending
):
    with pytest.raises(InvalidInput):
        InventoryMaterialResult(posting_value, pending)


def test_linking_resolves_inventory_scope_before_ids_and_preserves_only_same_target_line_identity():
    service, inventory, authority, _, ids = processor()
    selection = (MaterialSelection("binding", Quantity("1.5")),)
    linked = service.link("home", selection)
    assert len(linked) == 1 and linked[0].planned_quantity == Quantity("1.5") and ids.count == 1
    assert authority.calls[0] == ("home", "link") and inventory.calls[0][0] == "resolve"
    inventory.binding = replace(inventory.binding, revision=2, label="Updated")
    updated = service.link("home", selection, linked)
    assert (
        updated[0].line_id == linked[0].line_id
        and updated[0].binding.revision == 2
        and ids.count == 1
    )
    inventory.binding = replace(inventory.binding, location_id="different")
    replaced = service.link("home", selection, updated)
    assert replaced[0].line_id != linked[0].line_id and ids.count == 2
    assert service.link("home", (), linked) == ()


@pytest.mark.parametrize(
    "problem",
    [
        "unknown",
        "foreign",
        "wrong_reference",
        "wrong_type",
        "precision",
        "unavailable",
        "denied",
        "bad_actor",
        "bad_id",
    ],
)
def test_binding_failures_cannot_publish_forged_or_unvalidated_lines(problem):
    service, inventory, authority, _, ids = processor()
    if problem == "unknown":
        inventory.binding = None
    if problem == "foreign":
        inventory.binding = replace(inventory.binding, household_id="other")
    if problem == "wrong_reference":
        inventory.binding = replace(inventory.binding, reference_id="other")
    if problem == "wrong_type":
        inventory.binding = "forged"
    if problem == "precision":
        inventory.binding = replace(inventory.binding, precision=0)
    if problem == "unavailable":
        inventory.binding = IntegrationUnavailable("inventory_unavailable")
    if problem == "denied":
        authority.denied = True
    if problem == "bad_actor":
        authority.member_id = "bad id"
    if problem == "bad_id":
        ids.new = lambda: "bad id"
    with pytest.raises((InvalidInput, StorageFailure, IntegrationUnavailable, Forbidden)):
        service.link("home", (MaterialSelection("binding", Quantity("1.5")),))
    assert ids.count == 0
    if problem in ("denied", "bad_actor"):
        assert not inventory.calls


def test_completion_retains_ordinary_denied_usage_but_explicit_post_requires_current_authority():
    service, inventory, authority, _, _ = processor()
    authority.denied = True
    held = service.record_completion(intent())
    assert (
        held.state is State.PENDING_AUTHORIZATION and held.posting is None and not inventory.calls
    )
    with pytest.raises(Forbidden):
        service.post(held)
    authority.denied = False
    posted = service.post(held)
    assert posted.state is State.POSTED and inventory.calls[-1][1].actor_member_id == "operator"
    assert authority.calls[-1][1] is MaterialAction.POST


@pytest.mark.parametrize(
    "reason",
    [
        Pending.STOCK_SHORTAGE,
        Pending.BINDING_CHANGED,
        Pending.INVENTORY_UNAVAILABLE,
        Pending.PERMISSION_REQUIRED,
        Pending.AWAITING_INVENTORY,
    ],
)
def test_real_consumer_pending_contract_never_claims_a_movement(reason):
    service, inventory, _, _, _ = processor()
    inventory.result = InventoryMaterialResult(pending_reason=reason)
    held = service.record_completion(intent())
    assert held.pending_reason is reason and held.posting is None and held.needs_posting


def test_unavailability_and_missing_separate_or_zero_actuals_never_turn_into_automatic_effects():
    service, inventory, authority, _, _ = processor()
    inventory.result = IntegrationUnavailable("inventory_unavailable")
    held = service.record_completion(intent())
    assert held.pending_reason is Pending.INVENTORY_UNAVAILABLE and held.posting is None
    inventory.calls.clear()
    authority.calls.clear()
    for value in (intent(None), intent("0"), intent(mode=MaterialRecording.SEPARATE)):
        assert service.record_completion(value) is value
    assert not inventory.calls and not authority.calls
    with pytest.raises(Conflict):
        service.post(intent(None))
    with pytest.raises(Conflict):
        service.post(intent("0"))
    assert not inventory.calls


@pytest.mark.parametrize(
    "result",
    [
        None,
        "forged",
        InventoryMaterialResult(posting=replace(posting(intent()), household_id="other")),
        InventoryMaterialResult(posting=replace(posting(intent()), quantity=Quantity("3"))),
    ],
)
def test_malformed_consumer_proof_is_a_storage_contract_failure(result):
    service, inventory, _, _, _ = processor()
    inventory.result = result
    with pytest.raises(StorageFailure):
        service.post(intent())


def test_explicit_correct_and_dismiss_are_current_authorized_commands_not_stock_return_setters():
    service, inventory, authority, _, _ = processor()
    corrected = service.correct(intent(), Quantity("3"), "Actual was higher")
    assert corrected.state is State.CORRECTED and corrected.submitted_quantity == Quantity("2")
    assert authority.calls[-1][1] is MaterialAction.CORRECT
    inventory.calls.clear()
    unused = service.correct(intent(), Quantity("0"), "None used")
    assert unused.state is State.NOT_USED and not inventory.calls
    dismissed = service.dismiss(intent(None), "Not applicable")
    assert dismissed.state is State.DISMISSED and authority.calls[-1][1] is MaterialAction.DISMISS
    authority.denied = True
    with pytest.raises(Forbidden):
        service.correct(intent(), Quantity("3"), "Correct")
    with pytest.raises(Forbidden):
        service.dismiss(intent(), "Dismiss")


def test_bad_authority_and_revision_exhaustion_stop_before_inventory_effects():
    service, inventory, authority, _, _ = processor()
    authority.member_id = "bad id"
    with pytest.raises(StorageFailure):
        service.post(intent())
    authority.member_id = "operator"
    with pytest.raises(Conflict):
        service.post(replace(intent(), revision=2**63 - 1))
    assert not inventory.calls


def test_the_explicit_unavailable_adapter_never_creates_catalog_or_ledger_evidence():
    from domus.infrastructure.task_materials import UnavailableTaskInventory

    inventory = UnavailableTaskInventory()
    with pytest.raises(IntegrationUnavailable):
        inventory.resolve("home", "operator", "binding")
    result = inventory.settle(MaterialPostingRequest(intent(), "operator"))
    assert result.posting is None and result.pending_reason is Pending.INVENTORY_UNAVAILABLE


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_posting",
        "recording_quantity",
        "pending_missing_quantity",
        "pending_zero",
        "pending_confirmed",
        "settled_reason",
        "not_used_positive",
        "corrected_without_correction",
        "dismissed_confirmed",
    ],
)
def test_material_state_invariants_reject_impossible_projection_combinations(kind):
    posted = intent().confirm(posting(intent()), 110)
    original, changes = intent(), {}
    if kind == "wrong_posting":
        original, changes = posted, {"posting": "forged"}
    if kind == "recording_quantity":
        changes = {
            "state": State.PENDING_RECORDING,
            "pending_reason": Pending.ACTUAL_QUANTITY_REQUIRED,
        }
    if kind == "pending_missing_quantity":
        original, changes = (
            intent(None),
            {"state": State.PENDING_PROCESSING, "pending_reason": Pending.AWAITING_INVENTORY},
        )
    if kind == "pending_zero":
        original, changes = (
            intent("0"),
            {"state": State.PENDING_PROCESSING, "pending_reason": Pending.AWAITING_INVENTORY},
        )
    if kind == "pending_confirmed":
        original, changes = (
            posted,
            {"state": State.PENDING_PROCESSING, "pending_reason": Pending.AWAITING_INVENTORY},
        )
    if kind == "settled_reason":
        original, changes = intent("0"), {"pending_reason": Pending.AWAITING_INVENTORY}
    if kind == "not_used_positive":
        changes = {"state": State.NOT_USED, "pending_reason": None}
    if kind == "corrected_without_correction":
        original, changes = posted, {"state": State.CORRECTED}
    if kind == "dismissed_confirmed":
        original, changes = posted, {"state": State.DISMISSED, "reason": "Do not erase Inventory"}
    with pytest.raises(InvalidInput):
        replace(original, **changes)


def test_recording_does_not_coerce_actual_quantities_or_reuse_immutable_ledger_identities():
    with pytest.raises(InvalidInput):
        MaterialIntent.record(
            "intent",
            "home",
            "occurrence",
            "cycle",
            line(),
            "2",
            recorded_by="recorder",
            performed_at=90,
            recorded_at=100,
            recording_mode=MaterialRecording.REVIEW_ON_COMPLETION,
            authorized=True,
        )
    posted = intent().confirm(posting(intent()), 110)
    corrected = posted.correct(Quantity("3"), "Correct", 120)
    for changes in (
        {"movement_id": posted.posting.movement_id},
        {"inventory_operation_id": posted.posting.inventory_operation_id},
    ):
        with pytest.raises(InvalidInput, match="invalid_material_confirmation"):
            corrected.confirm(posting(corrected, posted_at=130, **changes), 140)


def test_generated_material_line_identity_collisions_fail_before_publication():
    service, inventory, _, _, ids = processor()
    template = line().binding
    inventory.resolve = lambda household, actor, reference: replace(
        template, reference_id=reference
    )
    ids.new = lambda: "colliding-line"
    with pytest.raises(StorageFailure):
        service.link(
            "home",
            (MaterialSelection("first", Quantity("1")), MaterialSelection("second", Quantity("1"))),
        )
