-- Frozen schema from 95458b84b6521b203fab3a257137f24978a03e82.
-- Independent upgrade input; never regenerate this fixture from the current schema.
CREATE TABLE installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1), instance_id TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('stable','edge')));
CREATE TABLE households(household_id TEXT PRIMARY KEY, singleton INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK(singleton=1), name TEXT NOT NULL, time_zone TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=1));
CREATE TABLE receipts(household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, result TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(household_id,actor_id,action,command_key));
CREATE TABLE audit(operation_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(household_id), actor_id TEXT NOT NULL, action TEXT NOT NULL, command_key TEXT NOT NULL, detail TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE outbox(position INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, household_id TEXT NOT NULL REFERENCES households(household_id), event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at INTEGER NOT NULL, delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)));
CREATE INDEX outbox_pending ON outbox(delivered,position);
INSERT INTO installation VALUES (1,'047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6','edge');
INSERT INTO households VALUES ('home',1,'Existing household','UTC',3);
INSERT INTO receipts VALUES ('home','ha_1','household.rename','old-key','old-digest','old-operation','{"revision":3}',100);
INSERT INTO audit VALUES ('old-operation','home','ha_1','household.rename','old-key','{"retained":true}',100);
INSERT INTO outbox(event_id,household_id,event_type,payload,created_at) VALUES ('old-operation','home','household.rename','{"revision":3}',100);
PRAGMA application_id=0x444F4D55;
PRAGMA user_version=1;
