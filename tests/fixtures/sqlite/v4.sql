-- Frozen schema 4 from immutable project source 143de3e79bf8aa02171b4123b794d222f4d4f231.
-- Seed: unchanged frozen v3.sql; history DDL/data mapping verified against that source.
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
CREATE TABLE retained_operations(household_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, position INTEGER NOT NULL UNIQUE CHECK(position>=1), current INTEGER NOT NULL CHECK(current IN (0,1)), archived_by TEXT, document TEXT NOT NULL, closed_recovery_id TEXT, PRIMARY KEY(household_id,actor_id,action,command_key));
INSERT INTO "retained_operations" VALUES('home','ha_admin','household.setup','setup','identity-2',1,1,NULL,'{"action":"household.setup","actor_id":"ha_admin","archived_by":null,"audit_detail":{"administrator_member_id":"identity-1","mapping_mode":"all_ha_administrators","transition":"household.configured"},"command_key":"setup","created_at":100,"current":true,"delivered":false,"event_payload":{"household_id":"home","revision":1},"household_id":"home","operation_id":"identity-2","payload_fingerprint":"fd81d9a903eff49c605ff960bfae80f61f684b2f1f12ff15fb363cd7bdea3c51","position":1,"result":{"administrator_member_id":"identity-1","household_id":"home","mapping_mode":"all_ha_administrators","member_id":"identity-1","policy_revision":1,"revision":1,"state":"configured"}}',NULL);
INSERT INTO "retained_operations" VALUES('home','human','household.update','a','operation-a',8,0,'restore-v4','{"action":"household.update","actor_id":"human","archived_by":"restore-v4","audit_detail":{"name":"a","revision":8},"command_key":"a","created_at":100,"current":false,"delivered":false,"event_payload":{"name":"a","revision":8},"household_id":"home","operation_id":"operation-a","payload_fingerprint":"9e098c9adc21df5506d6ed04d94cdee3363aa9752c60175d0db4242f6b9d311d","position":8,"result":{"name":"a","revision":8}}',NULL);
CREATE INDEX outbox_pending ON outbox(delivered,position);
CREATE INDEX recovery_pending ON recovery_requests(household_id,state,expires_at);
CREATE INDEX retained_recovery ON retained_operations(household_id,closed_recovery_id) WHERE current=0 AND closed_recovery_id IS NOT NULL;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('outbox',8);
COMMIT;
PRAGMA application_id=0x444F4D55;
PRAGMA user_version=4;
