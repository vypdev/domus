"""Daily schedules and admitted runs share the database's ordinary atomic writer."""

SCHEDULED_AUTOMATION_TABLES = {"automation_daily_schedules", "automation_scheduled_runs"}
SCHEDULED_AUTOMATION_STATEMENTS = (
    "CREATE TABLE automation_daily_schedules("
    "household_id TEXT NOT NULL, rule_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "grant_id TEXT NOT NULL, rule_revision INTEGER NOT NULL, control_revision INTEGER NOT NULL, "
    "next_at INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(household_id,rule_id), "
    "UNIQUE(household_id,grant_id), FOREIGN KEY(household_id,rule_id,rule_revision) "
    "REFERENCES automation_draft_revisions(household_id,rule_id,revision))",
    "CREATE TABLE automation_scheduled_runs("
    "household_id TEXT NOT NULL, trigger_key TEXT NOT NULL, rule_id TEXT NOT NULL, "
    "rule_revision INTEGER NOT NULL, grant_id TEXT NOT NULL, "
    "outcome TEXT NOT NULL CHECK(outcome IN ('queued','created','no_task','cancelled','denied')), "
    "admitted_at INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(household_id,trigger_key), "
    "FOREIGN KEY(household_id,rule_id,rule_revision) "
    "REFERENCES automation_draft_revisions(household_id,rule_id,revision))",
    "CREATE INDEX automation_scheduled_pending "
    "ON automation_scheduled_runs(household_id,outcome,admitted_at,trigger_key)",
    "CREATE INDEX automation_scheduled_history "
    "ON automation_scheduled_runs(household_id,rule_id,admitted_at DESC,trigger_key DESC)",
    "CREATE INDEX retained_scheduled_history ON retained_operations("
    "household_id,actor_id,json_extract(document,'$.result.run.admitted_at') DESC,"
    "command_key DESC) "
    "WHERE current=0 AND action IN ('automation.scheduled.admit','automation.scheduled.run')",
)
