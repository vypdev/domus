"""Scoped recurrence rows and deferred original evidence share the enclosing atomic commit."""

RECURRENCE_TABLES = {
    "recurrence_rules",
    "recurrence_progress",
    "recurrence_slots",
    "recurrence_frontiers",
    "recurrence_progress_evidence",
    "recurrence_relative_slots",
}
RECURRENCE_STATEMENTS = (
    "CREATE TABLE recurrence_frontiers(household_id TEXT PRIMARY KEY NOT NULL "
    "REFERENCES households(household_id), after_schedule_id TEXT, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "selected_at INTEGER NOT NULL CHECK(typeof(selected_at)='integer' AND selected_at>=0), "
    "document TEXT NOT NULL)",
    "CREATE UNIQUE INDEX recurrence_occurrence_scope "
    "ON task_occurrences(household_id,definition_id,occurrence_id)",
    "CREATE UNIQUE INDEX recurrence_cycle_scope "
    "ON task_cycles(household_id,occurrence_id,cycle_id)",
    "CREATE TABLE recurrence_rules(schedule_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, definition_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "pattern_revision INTEGER NOT NULL CHECK(typeof(pattern_revision)='integer' "
    "AND pattern_revision>=1 AND pattern_revision<=revision), "
    "state TEXT NOT NULL CHECK(state IN ('active','paused','retired')), "
    "timing_kind TEXT NOT NULL CHECK(timing_kind IN ('fixed_calendar','completion_relative')), "
    "document TEXT NOT NULL, "
    "UNIQUE(household_id,schedule_id), UNIQUE(household_id,schedule_id,definition_id), "
    "UNIQUE(household_id,schedule_id,pattern_revision,timing_kind), "
    "UNIQUE(household_id,schedule_id,definition_id,timing_kind), "
    "FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id), "
    "FOREIGN KEY(household_id,schedule_id,pattern_revision,timing_kind) "
    "REFERENCES recurrence_progress(household_id,schedule_id,pattern_revision,timing_kind) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE recurrence_progress(schedule_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL, pattern_revision INTEGER NOT NULL "
    "CHECK(typeof(pattern_revision)='integer' AND pattern_revision>=1), "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "timing_kind TEXT NOT NULL CHECK(timing_kind IN ('fixed_calendar','completion_relative')), "
    "document TEXT NOT NULL, UNIQUE(household_id,schedule_id,pattern_revision,timing_kind), "
    "FOREIGN KEY(household_id,schedule_id,pattern_revision,timing_kind) "
    "REFERENCES recurrence_rules(household_id,schedule_id,pattern_revision,timing_kind) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE UNIQUE INDEX recurrence_progress_revision "
    "ON recurrence_progress(household_id,schedule_id,revision)",
    "CREATE UNIQUE INDEX recurrence_current_definition "
    "ON recurrence_rules(household_id,definition_id) WHERE state!='retired'",
    "CREATE TABLE recurrence_progress_evidence(household_id TEXT NOT NULL, "
    "schedule_id TEXT NOT NULL, progress_revision INTEGER NOT NULL "
    "CHECK(typeof(progress_revision)='integer' AND progress_revision>=1), "
    "operation_id TEXT NOT NULL, evidence_fingerprint TEXT NOT NULL, "
    "PRIMARY KEY(household_id,schedule_id), "
    "FOREIGN KEY(household_id,schedule_id,progress_revision) "
    "REFERENCES recurrence_progress(household_id,schedule_id,revision) "
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
    "timing_kind TEXT NOT NULL CHECK(timing_kind='fixed_calendar'), "
    "document TEXT NOT NULL, PRIMARY KEY(household_id,slot_key), "
    "UNIQUE(household_id,occurrence_id), "
    "CHECK((nominal_kind='date' AND resolved_at IS NULL) OR "
    "(nominal_kind='time' AND typeof(resolved_at)='integer' AND resolved_at>=0)), "
    "FOREIGN KEY(household_id,schedule_id,definition_id,timing_kind) "
    "REFERENCES recurrence_rules(household_id,schedule_id,definition_id,timing_kind), "
    "FOREIGN KEY(household_id,definition_id,occurrence_id) "
    "REFERENCES task_occurrences(household_id,definition_id,occurrence_id), "
    "FOREIGN KEY(household_id,receipt_actor,receipt_action,slot_key) "
    "REFERENCES receipts(household_id,actor_id,action,command_key) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE recurrence_relative_slots(household_id TEXT NOT NULL, slot_key TEXT NOT NULL, "
    "schedule_id TEXT NOT NULL, definition_id TEXT NOT NULL, pattern_revision INTEGER NOT NULL "
    "CHECK(typeof(pattern_revision)='integer' AND pattern_revision>=1), "
    "occurrence_id TEXT NOT NULL, source_occurrence_id TEXT, source_cycle_id TEXT, "
    "created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0), "
    "receipt_actor TEXT NOT NULL CHECK(receipt_actor='system:recurrence'), "
    "receipt_action TEXT NOT NULL CHECK(receipt_action='recurrence.materialize'), "
    "timing_kind TEXT NOT NULL CHECK(timing_kind='completion_relative'), document TEXT NOT NULL, "
    "PRIMARY KEY(household_id,slot_key), UNIQUE(household_id,occurrence_id), "
    "CHECK((source_occurrence_id IS NULL)=(source_cycle_id IS NULL)), "
    "FOREIGN KEY(household_id,schedule_id,definition_id,timing_kind) "
    "REFERENCES recurrence_rules(household_id,schedule_id,definition_id,timing_kind), "
    "FOREIGN KEY(household_id,definition_id,occurrence_id) "
    "REFERENCES task_occurrences(household_id,definition_id,occurrence_id), "
    "FOREIGN KEY(household_id,source_occurrence_id,source_cycle_id) "
    "REFERENCES task_cycles(household_id,occurrence_id,cycle_id), "
    "FOREIGN KEY(household_id,receipt_actor,receipt_action,slot_key) "
    "REFERENCES receipts(household_id,actor_id,action,command_key) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE INDEX recurrence_rules_page ON recurrence_rules(household_id,state,schedule_id)",
    "CREATE INDEX recurrence_slots_page ON recurrence_slots(household_id,schedule_id,slot_key)",
    "CREATE INDEX recurrence_relative_slots_page "
    "ON recurrence_relative_slots(household_id,schedule_id,slot_key)",
)

RELATIVE_LIFECYCLE_TABLES = {"recurrence_relative_inbox", "recurrence_relative_closures"}
RELATIVE_LIFECYCLE_STATEMENTS = (
    "CREATE TABLE recurrence_relative_inbox(household_id TEXT NOT NULL "
    "REFERENCES households(household_id), position INTEGER NOT NULL "
    "CHECK(typeof(position)='integer' AND position>=1), "
    "event_key TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, actor_id TEXT NOT NULL, "
    "cycle_key TEXT NOT NULL, source_schedule_id TEXT, source_terminal INTEGER NOT NULL "
    "CHECK(typeof(source_terminal)='integer' AND source_terminal IN (0,1)), "
    "outcome_status TEXT, outcome_schedule_id TEXT, "
    "outcome_operation_id TEXT, outcome_occurrence_id TEXT, "
    "CHECK((outcome_status IS NULL)=(outcome_schedule_id IS NULL) AND "
    "(outcome_status IS NOT NULL OR "
    "(outcome_operation_id IS NULL AND outcome_occurrence_id IS NULL))), "
    "PRIMARY KEY(household_id,position), UNIQUE(household_id,event_key), "
    "FOREIGN KEY(household_id,source_schedule_id) "
    "REFERENCES recurrence_rules(household_id,schedule_id))",
    "CREATE INDEX recurrence_relative_pending ON recurrence_relative_inbox(household_id,position) "
    "WHERE outcome_status IS NULL",
    "CREATE INDEX recurrence_relative_pending_rule "
    "ON recurrence_relative_inbox(household_id,source_schedule_id,source_terminal DESC,position) "
    "WHERE outcome_status IS NULL",
    # Closures can outlive the rule, source cycle, and live receipt after compatible restoration.
    "CREATE TABLE recurrence_relative_closures(household_id TEXT NOT NULL, "
    "closure_key TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL, "
    "PRIMARY KEY(household_id,closure_key))",
)
