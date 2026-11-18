"""Bounded declarative rules and a pure explanation of proposed effects."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from domus.domain.errors import InvalidInput
from domus.domain.identity import validate_revision
from domus.domain.storage import JsonDocument, JsonObject, JsonValue, validate_identifier
from domus.domain.task_values import TaskContent

AUTOMATION_RULE_VERSION = 1
MAX_RULE_NODES = 64
MAX_CONDITION_DEPTH = 8


@dataclass(frozen=True, slots=True)
class StockCondition:
    product_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.product_id)


@dataclass(frozen=True, slots=True)
class ConditionGroup:
    kind: Literal["all", "any"]
    children: tuple[Condition, ...]

    def __post_init__(self) -> None:
        if self.kind not in ("all", "any") or type(self.children) is not tuple or not self.children:
            raise InvalidInput("invalid_automation_condition")


@dataclass(frozen=True, slots=True)
class NegatedCondition:
    child: Condition


type Condition = StockCondition | ConditionGroup | NegatedCondition
type ConditionKind = Literal["stock_below_minimum", "all", "any", "not"]


def _children(condition: Condition) -> tuple[Condition, ...]:
    if isinstance(condition, ConditionGroup):
        return condition.children
    if isinstance(condition, NegatedCondition):
        return (condition.child,)
    if isinstance(condition, StockCondition):
        return ()
    raise InvalidInput("invalid_automation_condition")


def _condition_value(condition: Condition) -> JsonObject:
    if isinstance(condition, StockCondition):
        return {"kind": "stock_below_minimum", "product_id": condition.product_id}
    if isinstance(condition, NegatedCondition):
        return {"kind": "not", "child": _condition_value(condition.child)}
    return {
        "kind": condition.kind,
        "children": [_condition_value(child) for child in condition.children],
    }


def _read_condition(value: JsonValue) -> Condition:
    match value:
        case {"kind": "stock_below_minimum", "product_id": str() as product, **extra} if not extra:
            return StockCondition(product)
        case {"kind": "not", "child": child, **extra} if not extra:
            return NegatedCondition(_read_condition(child))
        case {
            "kind": ("all" | "any") as kind,
            "children": list() as children,
            **extra,
        } if not extra:
            return ConditionGroup(kind, tuple(_read_condition(child) for child in children))
        case _:
            raise InvalidInput("invalid_automation_condition")


@dataclass(frozen=True, slots=True)
class AutomationRule:
    version: int
    trigger: Literal["manual"]
    condition: Condition | None
    task: TaskContent

    def __post_init__(self) -> None:
        if (
            type(self.version) is not int
            or self.version != AUTOMATION_RULE_VERSION
            or self.trigger != "manual"
            or not isinstance(self.task, TaskContent)
        ):
            raise InvalidInput("invalid_automation_rule")
        pending = [] if self.condition is None else [(self.condition, 1)]
        size = 2  # The manual trigger and the proposed action.
        while pending:
            condition, depth = pending.pop()
            if depth > MAX_CONDITION_DEPTH:
                raise InvalidInput("automation_condition_depth")
            size += 1
            children = _children(condition)
            if size + len(pending) + len(children) > MAX_RULE_NODES:
                raise InvalidInput("automation_rule_node_limit")
            pending.extend((child, depth + 1) for child in reversed(children))

    def document(self) -> JsonDocument:
        """Persist exactly what the version-one task proposal can represent."""
        if self.task != TaskContent(self.task.title):
            raise InvalidInput("invalid_automation_rule")
        return JsonDocument.from_value(
            {
                "version": self.version,
                "trigger": {"kind": self.trigger},
                "action": {"kind": "task.create", "title": self.task.title},
                "condition": None if self.condition is None else _condition_value(self.condition),
            }
        )

    def stock_products(self) -> tuple[str, ...]:
        pending = [] if self.condition is None else [self.condition]
        products: dict[str, None] = {}
        while pending:
            condition = pending.pop()
            if isinstance(condition, StockCondition):
                products[condition.product_id] = None
            pending.extend(reversed(_children(condition)))
        return tuple(products)

    @classmethod
    def from_document(cls, document: JsonDocument) -> AutomationRule:
        match document.decode():
            case {
                "version": int() as version,
                "trigger": {"kind": "manual", **trigger_extra},
                "action": {"kind": "task.create", "title": str() as title, **action_extra},
                "condition": condition,
                **extra,
            } if not (extra or trigger_extra or action_extra):
                return cls(
                    version,
                    "manual",
                    None if condition is None else _read_condition(condition),
                    TaskContent(title),
                )
            case _:
                raise InvalidInput("invalid_automation_rule")


@dataclass(frozen=True, slots=True)
class AutomationDraft:
    rule_id: str
    revision: int
    rule: AutomationRule

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id)
        validate_revision(self.revision)


@dataclass(frozen=True, slots=True)
class AutomationControl:
    """Identify the exact configured definition independently of the latest draft."""

    rule_id: str
    rule_revision: int
    control_revision: int
    enabled: bool

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id)
        validate_revision(self.rule_revision)
        validate_revision(self.control_revision)
        if type(self.enabled) is not bool:
            raise InvalidInput("invalid_automation_control")


@dataclass(frozen=True, slots=True)
class ConditionDecision:
    path: tuple[int, ...]
    kind: ConditionKind
    matched: bool
    product_id: str | None = None


@dataclass(frozen=True, slots=True)
class AutomationSimulation:
    version: int
    trigger: Literal["manual"]
    task_title: str
    would_create: bool
    conditions: tuple[ConditionDecision, ...]


def simulate(rule: AutomationRule, below_minimum: Callable[[str], bool]) -> AutomationSimulation:
    decisions: list[ConditionDecision] = []

    def evaluate(condition: Condition, path: tuple[int, ...]) -> bool:
        if isinstance(condition, StockCondition):
            matched = below_minimum(condition.product_id)
            decisions.append(
                ConditionDecision(path, "stock_below_minimum", matched, condition.product_id)
            )
        elif isinstance(condition, NegatedCondition):
            matched = not evaluate(condition.child, (*path, 0))
            decisions.append(ConditionDecision(path, "not", matched))
        else:
            matches = tuple(
                evaluate(child, (*path, index)) for index, child in enumerate(condition.children)
            )
            matched = all(matches) if condition.kind == "all" else any(matches)
            decisions.append(ConditionDecision(path, condition.kind, matched))
        return matched

    would_create = rule.condition is None or evaluate(rule.condition, ())
    return AutomationSimulation(
        rule.version, rule.trigger, rule.task.title, would_create, tuple(decisions)
    )
