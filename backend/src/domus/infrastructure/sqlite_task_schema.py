"""Task table constraints preserve scoped snapshots and both sides of an active cycle."""

TASK_TABLES = {"task_policy", "task_definitions", "task_occurrences", "task_cycles"}
TASK_STATEMENTS = (
    "CREATE UNIQUE INDEX task_member_scope ON members(household_id,member_id)",
    "CREATE TABLE task_policy(household_id TEXT PRIMARY KEY NOT NULL "
    "REFERENCES households(household_id), "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "document TEXT NOT NULL)",
    "CREATE TABLE task_definitions(definition_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL REFERENCES task_policy(household_id), "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "state TEXT NOT NULL CHECK(state IN ('draft','active','paused','archived')), "
    "document TEXT NOT NULL, UNIQUE(household_id,definition_id))",
    "CREATE TABLE task_occurrences(occurrence_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "definition_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "state TEXT NOT NULL CHECK(state IN "
    "('draft','available','assigned','in_progress','blocked','completed','cancelled','skipped')), "
    "current_cycle_id TEXT, current_cycle_revision INTEGER "
    "CHECK(current_cycle_revision IS NULL OR "
    "(typeof(current_cycle_revision)='integer' AND current_cycle_revision>=1)), "
    "document TEXT NOT NULL, "
    "UNIQUE(household_id,occurrence_id), "
    "UNIQUE(household_id,occurrence_id,current_cycle_id,current_cycle_revision), "
    "CHECK((state='completed' AND current_cycle_id IS NOT NULL "
    "AND current_cycle_revision IS NOT NULL) OR "
    "(state!='completed' AND current_cycle_id IS NULL AND current_cycle_revision IS NULL)), "
    "FOREIGN KEY(household_id,definition_id) "
    "REFERENCES task_definitions(household_id,definition_id), "
    "FOREIGN KEY(household_id,occurrence_id,current_cycle_id,current_cycle_revision) "
    "REFERENCES task_cycles(household_id,active_occurrence_id,cycle_id,revision) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE task_cycles(cycle_id TEXT PRIMARY KEY NOT NULL, "
    "household_id TEXT NOT NULL REFERENCES households(household_id), "
    "occurrence_id TEXT NOT NULL, active_occurrence_id TEXT, "
    "recorded_by TEXT NOT NULL, verified_by TEXT, "
    "revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=1), "
    "closed_at INTEGER CHECK(closed_at IS NULL OR (typeof(closed_at)='integer' AND closed_at>=0)), "
    "document TEXT NOT NULL, "
    "UNIQUE(household_id,active_occurrence_id,cycle_id,revision), "
    "CHECK((closed_at IS NULL AND active_occurrence_id IS occurrence_id) OR "
    "(closed_at IS NOT NULL AND active_occurrence_id IS NULL)), "
    "FOREIGN KEY(household_id,occurrence_id) "
    "REFERENCES task_occurrences(household_id,occurrence_id) DEFERRABLE INITIALLY DEFERRED, "
    "FOREIGN KEY(household_id,recorded_by) REFERENCES members(household_id,member_id), "
    "FOREIGN KEY(household_id,verified_by) REFERENCES members(household_id,member_id), "
    "FOREIGN KEY(household_id,active_occurrence_id,cycle_id,revision) "
    "REFERENCES task_occurrences(household_id,occurrence_id,"
    "current_cycle_id,current_cycle_revision) "
    "DEFERRABLE INITIALLY DEFERRED)",
    "CREATE INDEX task_definitions_page ON task_definitions(household_id,state,definition_id)",
    "CREATE INDEX task_occurrences_page ON task_occurrences(household_id,state,occurrence_id)",
    "CREATE INDEX task_occurrences_definition "
    "ON task_occurrences(household_id,definition_id,occurrence_id)",
    "CREATE INDEX task_cycles_page ON task_cycles(household_id,occurrence_id,cycle_id)",
    "CREATE UNIQUE INDEX task_one_open_cycle ON task_cycles(household_id,occurrence_id) "
    "WHERE closed_at IS NULL",
)
