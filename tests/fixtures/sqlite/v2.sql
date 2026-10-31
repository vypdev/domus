-- Frozen schema/data from ddc90faa5964509ed154090f8c8070f743e02370.
-- Independent migration input; never regenerate from the current schema.
BEGIN TRANSACTION;
CREATE TABLE audit(operation_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, detail TEXT NOT NULL, created_at INTEGER NOT NULL);
INSERT INTO "audit" VALUES('old-operation','home','ha_1','household.rename','old-key','{"retained":true}',100);
CREATE TABLE household_policy(household_id TEXT PRIMARY KEY REFERENCES households(household_id), mapping_mode TEXT NOT NULL, target_ha_user_id TEXT, revision INTEGER NOT NULL CHECK(revision>=1), adjustments TEXT NOT NULL, CHECK((mapping_mode='all_ha_administrators' AND target_ha_user_id IS NULL) OR (mapping_mode IN ('setup_administrator','selected_ha_user') AND target_ha_user_id IS NOT NULL)));
CREATE TABLE households(household_id TEXT PRIMARY KEY, singleton INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK(singleton=1), name TEXT NOT NULL, time_zone TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1));
INSERT INTO "households" VALUES('home',1,'Existing household','UTC',3);
CREATE TABLE installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1), instance_id TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('stable','edge')));
INSERT INTO "installation" VALUES(1,'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6','edge');
CREATE TABLE members(member_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), ha_user_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('administrator','adult','restricted','viewer')), status TEXT NOT NULL CHECK(status IN ('pending','active','suspended','archived')), revision INTEGER NOT NULL CHECK(revision>=1), exceptions TEXT NOT NULL, UNIQUE(household_id,ha_user_id));
CREATE TABLE outbox(position INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, household_id TEXT NOT NULL REFERENCES households(household_id), event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)));
INSERT INTO "outbox" VALUES(1,'old-operation','home','household.rename','{"revision":3}',100,0);
CREATE TABLE receipts(household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, result TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(household_id,actor_id,action,command_key));
INSERT INTO "receipts" VALUES('home','ha_1','household.rename','old-key','old-digest','old-operation','{"revision":3}',100);
CREATE INDEX outbox_pending ON outbox(delivered,position);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('outbox',1);
COMMIT;
PRAGMA application_id=0x444F4D55;
PRAGMA user_version=2;
