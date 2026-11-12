"""Bounded declarative rules and a pure explanation of proposed effects."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from domus.domain.errors import InvalidInput
from domus.domain.storage import validate_identifier
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
