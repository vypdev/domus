"""SQLite storage for reward catalog, reserved cost, spending, and funding history."""

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.identity import Role
from domus.domain.rewards import (
    FundingChange,
    FundingSource,
    Redemption,
    RedemptionStage,
    RewardDecision,
    RewardOffer,
    RewardSetting,
    RewardSpend,
)
from domus.domain.storage import JsonDocument
from domus.infrastructure.sqlite_points import SQLitePoints

REWARD_TABLES = {
    "reward_settings",
    "reward_offers",
    "reward_redemptions",
    "reward_spends",
    "reward_funding_changes",
}
REWARD_STATEMENTS = (
    "CREATE TABLE reward_settings(household_id TEXT PRIMARY KEY REFERENCES households,"
    "enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), "
    "revision INTEGER NOT NULL CHECK(revision>=1))",
    "CREATE TABLE reward_offers(household_id TEXT NOT NULL REFERENCES households,"
    "offer_id TEXT NOT NULL, document TEXT NOT NULL CHECK(json_valid(document)),"
    "PRIMARY KEY(household_id,offer_id))",
    "CREATE TABLE reward_redemptions(position INTEGER PRIMARY KEY AUTOINCREMENT,"
    "household_id TEXT NOT NULL REFERENCES households, redemption_id TEXT NOT NULL,"
    "member_id TEXT NOT NULL, offer_id TEXT NOT NULL, "
    "cost_minor INTEGER NOT NULL CHECK(cost_minor>0),"
    "stage TEXT NOT NULL CHECK(stage IN "
    "('requested','approved','funding_hold','delivered','cancelled')),"
    "document TEXT NOT NULL CHECK(json_valid(document)), UNIQUE(household_id,redemption_id),"
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id),"
    "FOREIGN KEY(household_id,offer_id) REFERENCES reward_offers(household_id,offer_id))",
    "CREATE INDEX reward_member_requests ON reward_redemptions(household_id,member_id,position)",
    "CREATE INDEX reward_member_reservations ON reward_redemptions(household_id,member_id,stage)"
    " WHERE stage IN ('requested','approved','funding_hold')",
    "CREATE TABLE reward_spends(household_id TEXT NOT NULL, redemption_id TEXT NOT NULL,"
    "member_id TEXT NOT NULL, cost_minor INTEGER NOT NULL CHECK(cost_minor>0),"
    "posted_at INTEGER NOT NULL CHECK(posted_at>=0), title TEXT NOT NULL,"
    "PRIMARY KEY(household_id,redemption_id),"
    "FOREIGN KEY(household_id,redemption_id) REFERENCES "
    "reward_redemptions(household_id,redemption_id),"
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id))",
    "CREATE INDEX reward_member_spending ON reward_spends(household_id,member_id,posted_at)",
    "CREATE TABLE reward_funding_changes(household_id TEXT NOT NULL, redemption_id TEXT NOT NULL,"
    "revision INTEGER NOT NULL CHECK(revision>1), "
    "source TEXT NOT NULL CHECK(source IN ('points','cancellation')),"
    "source_id TEXT NOT NULL, stage TEXT NOT NULL CHECK(stage IN ('approved','funding_hold')),"
    "occurred_at INTEGER NOT NULL CHECK(occurred_at>=0), "
    "PRIMARY KEY(household_id,redemption_id,revision),"
    "UNIQUE(household_id,redemption_id,source,source_id),"
    "FOREIGN KEY(household_id,redemption_id) REFERENCES "
    "reward_redemptions(household_id,redemption_id))",
)


def _setting(row: sqlite3.Row) -> RewardSetting:
    return RewardSetting(bool(row["enabled"]), row["revision"])


def _offer(row: sqlite3.Row) -> RewardOffer:
    try:
        value: dict[str, Any] = JsonDocument(row["document"]).decode()
        value["eligible_roles"] = tuple(Role(role) for role in value["eligible_roles"])
        offer = RewardOffer(**value)
        if offer.offer_id != row["offer_id"]:
            raise InvalidInput("invalid_reward_offer")
        return offer
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_reward_offer") from None


def _decision(value: dict[str, Any] | None) -> RewardDecision | None:
    return None if value is None else RewardDecision(**value)


def _redemption(row: sqlite3.Row) -> Redemption:
    try:
        value: dict[str, Any] = JsonDocument(row["document"]).decode()
        value["stage"] = RedemptionStage(value["stage"])
        value["approval"] = _decision(value["approval"])
        value["closed"] = _decision(value["closed"])
        redemption = Redemption(**value)
        if (
            redemption.redemption_id != row["redemption_id"]
            or redemption.member_id != row["member_id"]
            or redemption.offer_id != row["offer_id"]
            or redemption.stage != row["stage"]
            or redemption.cost_minor != row["cost_minor"]
        ):
            raise InvalidInput("invalid_redemption")
        return redemption
    except InvalidInput, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_redemption") from None


def _spend(row: sqlite3.Row) -> RewardSpend:
    return RewardSpend(row["redemption_id"], row["title"], row["cost_minor"], row["posted_at"])


@dataclass
class SQLiteRewards:
    connection: sqlite3.Connection

    def setting(self, home: str) -> RewardSetting | None:
        row = self.connection.execute(
            "SELECT * FROM reward_settings WHERE household_id=?", (home,)
        ).fetchone()
        return None if row is None else _setting(row)

    def save_setting(self, home: str, setting: RewardSetting) -> None:
        self.connection.execute(
            "INSERT INTO reward_settings VALUES(?,?,?) ON CONFLICT(household_id) "
            "DO UPDATE SET enabled=excluded.enabled,revision=excluded.revision",
            (home, setting.enabled, setting.revision),
        )

    def offer(self, home: str, offer_id: str) -> RewardOffer | None:
        row = self.connection.execute(
            "SELECT * FROM reward_offers WHERE household_id=? AND offer_id=?", (home, offer_id)
        ).fetchone()
        return None if row is None else _offer(row)

    def catalog(self, home: str) -> tuple[RewardOffer, ...]:
        return tuple(
            _offer(row)
            for row in self.connection.execute(
                "SELECT * FROM reward_offers WHERE household_id=? ORDER BY offer_id", (home,)
            )
        )

    def save_offer(self, home: str, offer: RewardOffer) -> None:
        self.connection.execute(
            "INSERT INTO reward_offers VALUES(?,?,?) ON CONFLICT(household_id,offer_id) "
            "DO UPDATE SET document=excluded.document",
            (home, offer.offer_id, JsonDocument(json.dumps(asdict(offer))).encoded),
        )

    def redemption(self, home: str, redemption_id: str) -> Redemption | None:
        row = self.connection.execute(
            "SELECT * FROM reward_redemptions WHERE household_id=? AND redemption_id=?",
            (home, redemption_id),
        ).fetchone()
        return None if row is None else _redemption(row)

    def save_redemption(self, home: str, redemption: Redemption) -> None:
        self.connection.execute(
            "INSERT INTO reward_redemptions(household_id,redemption_id,member_id,offer_id,"
            "cost_minor,stage,document) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(household_id,redemption_id)"
            " DO UPDATE SET stage=excluded.stage,document=excluded.document",
            (
                home,
                redemption.redemption_id,
                redemption.member_id,
                redemption.offer_id,
                redemption.cost_minor,
                redemption.stage,
                JsonDocument(json.dumps(asdict(redemption))).encoded,
            ),
        )

    def requests(
        self, home: str, member_id: str, *, after: str | None, limit: int
    ) -> tuple[Redemption, ...]:
        return tuple(
            _redemption(row)
            for row in self.connection.execute(
                "SELECT * FROM reward_redemptions WHERE household_id=:home AND member_id=:member "
                "AND (:after IS NULL OR position<(SELECT position FROM reward_redemptions "
                "WHERE household_id=:home AND member_id=:member AND redemption_id=:after)) "
                "ORDER BY position DESC LIMIT :limit",
                {"home": home, "member": member_id, "after": after, "limit": limit},
            )
        )

    def approved(self, home: str, member_id: str) -> tuple[Redemption, ...]:
        return tuple(
            _redemption(row)
            for row in self.connection.execute(
                "SELECT * FROM reward_redemptions WHERE household_id=? AND member_id=? "
                "AND stage IN ('approved','funding_hold') ORDER BY position",
                (home, member_id),
            )
        )

    def funding(self, home: str, change: FundingChange) -> None:
        self.connection.execute(
            "INSERT INTO reward_funding_changes VALUES(?,?,?,?,?,?,?)",
            (
                home,
                change.redemption_id,
                change.revision,
                change.source,
                change.source_id,
                change.stage,
                change.occurred_at,
            ),
        )

    def spent(self, home: str, member_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(cost_minor),0) FROM reward_spends "
            "WHERE household_id=? AND member_id=?",
            (home, member_id),
        ).fetchone()
        return int(row[0])

    def reservations(self, home: str, member_id: str) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(cost_minor),0),COUNT(*) FROM reward_redemptions "
            "WHERE household_id=? AND member_id=? "
            "AND stage IN ('requested','approved','funding_hold')",
            (home, member_id),
        ).fetchone()
        return int(row[0]), int(row[1])

    def post_spend(self, home: str, member_id: str, spend: RewardSpend) -> None:
        self.connection.execute(
            "INSERT INTO reward_spends VALUES(?,?,?,?,?,?)",
            (home, spend.redemption_id, member_id, spend.cost_minor, spend.posted_at, spend.title),
        )

    def spending_totals(self, home: str, member_id: str, start: int, end: int) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(cost_minor),0),COUNT(*) FROM reward_spends "
            "WHERE household_id=? AND member_id=? AND posted_at>=? AND posted_at<?",
            (home, member_id, start, end),
        ).fetchone()
        return int(row[0]), int(row[1])

    def spending(
        self, home: str, member_id: str, start: int, end: int, *, limit: int
    ) -> tuple[RewardSpend, ...]:
        return tuple(
            _spend(row)
            for row in self.connection.execute(
                "SELECT * FROM reward_spends WHERE household_id=? AND member_id=? AND posted_at>=? "
                "AND posted_at<? ORDER BY posted_at DESC,redemption_id DESC LIMIT ?",
                (home, member_id, start, end, limit),
            )
        )


def _funding(row: sqlite3.Row) -> FundingChange:
    return FundingChange(
        row["redemption_id"],
        row["revision"],
        FundingSource(row["source"]),
        row["source_id"],
        RedemptionStage(row["stage"]),
        row["occurred_at"],
    )


def _verify_funding_source(
    connection: sqlite3.Connection,
    repository: SQLiteRewards,
    home: str,
    member_id: str,
    event: FundingChange,
) -> None:
    if event.source is FundingSource.POINTS:
        matching = connection.execute(
            "SELECT 1 FROM points_task_receipts p JOIN json_each(p.document,'$.shares') share "
            "WHERE p.household_id=? AND p.event_id=? AND p.effect>0 "
            "AND json_extract(p.document,'$.posted_at')=? "
            "AND json_extract(share.value,'$[0]')=? AND json_extract(share.value,'$[1]')<>0",
            (home, event.source_id, event.occurred_at, member_id),
        ).fetchone()
        if matching is None:
            raise StorageFailure("invalid_reward_funding")
        return
    origin = repository.redemption(home, event.source_id)
    if (
        origin is None
        or origin.stage is not RedemptionStage.CANCELLED
        or origin.member_id != member_id
        or origin.closed is None
        or origin.closed.at != event.occurred_at
    ):
        raise StorageFailure("invalid_reward_funding")


def verify_reward_records(connection: sqlite3.Connection) -> None:
    repository = SQLiteRewards(connection)
    points = SQLitePoints(connection)
    for row in connection.execute("SELECT * FROM reward_settings"):
        _setting(row)
    for row in connection.execute("SELECT * FROM reward_offers"):
        _offer(row)
    for row in connection.execute("SELECT * FROM reward_redemptions"):
        redemption = _redemption(row)
        home = row["household_id"]
        spend = connection.execute(
            "SELECT * FROM reward_spends WHERE household_id=? AND redemption_id=?",
            (home, redemption.redemption_id),
        ).fetchone()
        if redemption.stage is RedemptionStage.DELIVERED:
            assert redemption.closed is not None
            expected = RewardSpend(
                redemption.redemption_id,
                redemption.title,
                redemption.cost_minor,
                redemption.closed.at,
            )
            if (
                spend is None
                or spend["member_id"] != redemption.member_id
                or _spend(spend) != expected
            ):
                raise StorageFailure("invalid_reward_spend")
        elif spend is not None:
            raise StorageFailure("invalid_reward_spend")
        if redemption.stage in {RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD}:
            reserved, _ = repository.reservations(home, redemption.member_id)
            posted = points.member_balance(home, redemption.member_id) - repository.spent(
                home, redemption.member_id
            )
            if (posted < reserved) != (redemption.stage is RedemptionStage.FUNDING_HOLD):
                raise StorageFailure("invalid_reward_funding")
        for entry in connection.execute(
            "SELECT * FROM reward_funding_changes WHERE household_id=? AND redemption_id=? "
            "ORDER BY revision",
            (home, redemption.redemption_id),
        ):
            event = _funding(entry)
            if (
                redemption.approval is None
                or event.revision > redemption.revision
                or event.occurred_at < redemption.approval.at
            ):
                raise StorageFailure("invalid_reward_funding")
            _verify_funding_source(connection, repository, home, redemption.member_id, event)
