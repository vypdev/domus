-- Frozen schema/data from 002a982ee60b8aa22a707de402ab1e8fc0306be5.
-- Independent upgrade input; never regenerate from the current schema.
BEGIN TRANSACTION;
CREATE TABLE audit(operation_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, detail TEXT NOT NULL, created_at INTEGER NOT NULL);
INSERT INTO "audit" VALUES('identity-2','home','ha_admin','household.setup','setup','{"administrator_member_id":"identity-1","mapping_mode":"all_ha_administrators","transition":"household.configured"}',100);
CREATE TABLE household_policy(household_id TEXT PRIMARY KEY REFERENCES households(household_id), mapping_mode TEXT NOT NULL, target_ha_user_id TEXT, revision INTEGER NOT NULL CHECK(revision>=1), adjustments TEXT NOT NULL, CHECK((mapping_mode='all_ha_administrators' AND target_ha_user_id IS NULL) OR (mapping_mode IN ('setup_administrator','selected_ha_user') AND target_ha_user_id IS NOT NULL)));
INSERT INTO "household_policy" VALUES('home','all_ha_administrators',NULL,1,'{"rules":[]}');
CREATE TABLE households(household_id TEXT PRIMARY KEY, singleton INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK(singleton=1), name TEXT NOT NULL, time_zone TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1));
INSERT INTO "households" VALUES('home',1,'Home','UTC',1);
CREATE TABLE installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1), instance_id TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('stable','edge')));
INSERT INTO "installation" VALUES(1,'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6','edge');
CREATE TABLE members(member_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), ha_user_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('administrator','adult','restricted','viewer')), status TEXT NOT NULL CHECK(status IN ('pending','active','suspended','archived')), revision INTEGER NOT NULL CHECK(revision>=1), exceptions TEXT NOT NULL, UNIQUE(household_id,ha_user_id));
INSERT INTO "members" VALUES('identity-1','home','ha_admin','viewer','active',1,'{"rules":[]}');
CREATE TABLE outbox(position INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, household_id TEXT NOT NULL REFERENCES households(household_id), event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)));
INSERT INTO "outbox" VALUES(1,'identity-2','home','household.setup','{"household_id":"home","revision":1}',100,0);
CREATE TABLE receipts(household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, result TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(household_id,actor_id,action,command_key));
INSERT INTO "receipts" VALUES('home','ha_admin','household.setup','setup','fd81d9a903eff49c605ff960bfae80f61f684b2f1f12ff15fb363cd7bdea3c51','identity-2','{"administrator_member_id":"identity-1","household_id":"home","mapping_mode":"all_ha_administrators","member_id":"identity-1","policy_revision":1,"revision":1,"state":"configured"}',100);
CREATE TABLE recovery_requests(request_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), target_ha_user_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1), state TEXT NOT NULL CHECK(state IN ('pending','approved','consumed','canceled')), created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, detail TEXT NOT NULL);
CREATE INDEX outbox_pending ON outbox(delivered,position);
CREATE INDEX recovery_pending ON recovery_requests(household_id,state,expires_at);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('outbox',1);
COMMIT;
PRAGMA application_id=0x444F4D55;
PRAGMA user_version=3;
