"""Schema9 adds separate public/private member records without rewriting historical facts."""

PROFILE_TABLES = {"member_presentations", "member_preferences"}
PROFILE_STATEMENTS = (
    "CREATE TABLE member_presentations(member_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, alias TEXT, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id), "
    "CHECK(alias IS NULL OR (typeof(alias)='text' AND length(alias) BETWEEN 1 AND 80)))",
    "CREATE TABLE member_preferences(member_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, locale TEXT CHECK(locale IS NULL OR locale IN ('en','es')), "
    "routine_participation_summaries INTEGER NOT NULL "
    "CHECK(typeof(routine_participation_summaries)='integer' "
    "AND routine_participation_summaries IN (0,1)), "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "FOREIGN KEY(household_id,member_id) REFERENCES members(household_id,member_id))",
    "INSERT INTO member_presentations(member_id,household_id,alias,revision) "
    "SELECT member_id,household_id,NULL,1 FROM members",
    "INSERT INTO member_preferences(member_id,household_id,locale,"
    "routine_participation_summaries,revision) SELECT member_id,household_id,NULL,1,1 FROM members",
)
