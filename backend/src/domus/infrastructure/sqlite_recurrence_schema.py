"""Scoped recurrence rows and deferred original evidence share the enclosing atomic commit."""

RECURRENCE_TABLES = {
    "recurrence_rules",
    "recurrence_progress",
    "recurrence_slots",
    "recurrence_frontiers",
}
RECURRENCE_STATEMENTS = (
    "CREATE TABLE recurrence_frontiers(household_id TEXT PRIMARY KEY NOT NULL "
    "REFERENCES households(household_id), after_schedule_id TEXT, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "selected_at INTEGER NOT NULL CHECK(typeof(selected_at)='integer' AND selected_at>=0), "
    "document TEXT NOT NULL)",
    "CREATE UNIQUE INDEX recurrence_occurrence_scope "
    "ON task_occurrences(household_id,definition_id,occurrence_id)",
    "CREATE TABLE recurrence_rules(schedule_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, definition_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "pattern_revision INTEGER NOT NULL CHECK(typeof(pattern_revision)='integer' "
    "AND pattern_revision>=1 AND pattern_revision<=revision), "
    "state TEXT NOT NULL CHECK(state IN ('active','paused','retired')), document TEXT NOT NULL, "
    "UNIQUE(household_id,schedule_id), UNIQUE(household_id,schedule_id,definition_id), "
    "UNIQUE(household_id,schedule_id,pattern_revision), "
    "FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id), "
    "FOREIGN KEY(household_id,schedule_id,pattern_revision) "
    "REFERENCES recurrence_progress(household_id,schedule_id,pattern_revision) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE recurrence_progress(schedule_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, pattern_revision INTEGER NOT NULL "
    "CHECK(typeof(pattern_revision)='integer' AND pattern_revision>=1), "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "document TEXT NOT NULL, UNIQUE(household_id,schedule_id,pattern_revision), "
    "FOREIGN KEY(household_id,schedule_id,pattern_revision) "
    "REFERENCES recurrence_rules(household_id,schedule_id,pattern_revision) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE recurrence_slots(household_id TEXT NOT NULL, slot_key TEXT NOT NULL, "
    "schedule_id TEXT NOT NULL, definition_id TEXT NOT NULL, "
    "pattern_revision INTEGER NOT NULL "
    "CHECK(typeof(pattern_revision)='integer' AND pattern_revision>=1), "
    "occurrence_id TEXT NOT NULL, "
    "nominal_kind TEXT NOT NULL CHECK(nominal_kind IN ('date','time')), "
    "nominal_value TEXT NOT NULL, resolved_at INTEGER, "
    "created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0), "
    "receipt_actor TEXT NOT NULL CHECK(receipt_actor='system:recurrence'), "
    "receipt_action TEXT NOT NULL CHECK(receipt_action='recurrence.materialize'), "
    "document TEXT NOT NULL, PRIMARY KEY(household_id,slot_key), "
    "UNIQUE(household_id,occurrence_id), "
    "CHECK((nominal_kind='date' AND resolved_at IS NULL) OR "
    "(nominal_kind='time' AND typeof(resolved_at)='integer' AND resolved_at>=0)), "
    "FOREIGN KEY(household_id,schedule_id,definition_id) "
    "REFERENCES recurrence_rules(household_id,schedule_id,definition_id), "
    "FOREIGN KEY(household_id,definition_id,occurrence_id) "
    "REFERENCES task_occurrences(household_id,definition_id,occurrence_id), "
    "FOREIGN KEY(household_id,receipt_actor,receipt_action,slot_key) "
    "REFERENCES receipts(household_id,actor_id,action,command_key) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE INDEX recurrence_rules_page ON recurrence_rules(household_id,state,schedule_id)",
    "CREATE INDEX recurrence_slots_page ON recurrence_slots(household_id,schedule_id,slot_key)",
)
