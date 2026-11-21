/** Generated from actual Domus Edge.57 client sources and their runtime dependencies.
 * Source: 272b5e8436588b5fab090622d19298371a6dc33c; see edge57-task-journal.provenance.json.
 * Compatibility test fixture only. Do not use in the product or edit by hand.
 */
// Edge.57 source: frontend/src/application/ports.ts
var JournalStorageError = class extends Error {
	code;
	constructor(code) {
		super(code);
		this.code = code;
		this.name = "JournalStorageError";
	}
};
var EntryReadError = class extends Error {
	code;
	constructor(code) {
		super(code);
		this.code = code;
		this.name = "EntryReadError";
	}
};
// Edge.57 source: frontend/src/domain/journal.ts
var JOURNAL_LIFETIME = 36e5;
var JournalError = class extends Error {
	code;
	constructor(code) {
		super(code);
		this.code = code;
		this.name = "JournalError";
	}
};
function invalid() {
	throw new JournalError("invalid_journal");
}
function object$1(value, keys) {
	if (typeof value !== "object" || value === null || Array.isArray(value) || Object.keys(value).length !== keys.length || !keys.every((key) => Object.hasOwn(value, key))) return invalid();
	return value;
}
function identifier(value) {
	return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value);
}
function scope$2(value) {
	const item = object$1(value, [
		"installationId",
		"channel",
		"subject"
	]);
	if (typeof item.installationId !== "string" || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/u.test(item.installationId) || item.channel !== "stable" && item.channel !== "edge" || !identifier(item.subject)) return invalid();
	return Object.freeze({
		installationId: item.installationId,
		channel: item.channel,
		subject: item.subject
	});
}
function time$1(value) {
	if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new JournalError("invalid_journal_time");
	return value;
}
function snapshot$1(context, observedAt, records) {
	return Object.freeze({
		version: 1,
		context,
		observedAt,
		records: Object.freeze(records)
	});
}
function emptyJournal(context, now) {
	return snapshot$1(scope$2(context), time$1(now), []);
}
// Edge.57 source: frontend/src/domain/administration.ts
var AdministrationError = class extends Error {
	code;
	constructor(code) {
		super(code);
		this.code = code;
		this.name = "AdministrationError";
	}
};
var MAX_REVISION = 9223372036854775807n;
/** Decimal text is the browser value, independently of the integer HTTP representation. */
function revisionValue(value) {
	if (typeof value !== "string" || value.length === 0 || value.length > 19 || value[0] === "0" || /[^0-9]/u.test(value) || BigInt(value) > MAX_REVISION) throw new AdministrationError("invalid_revision");
	return value;
}
function civilDate(value) {
	if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/u.test(value) || value < "1970-01-01") return false;
	const parsed = Date.parse(value + "T00:00:00Z");
	return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}
// Edge.57 source: frontend/src/domain/point-allocation.ts
function check(value) {
	if (!value) throw new Error("invalid_points_allocation");
}
function allocationFingerprint(value) {
	check(typeof value === "string" && /^[a-f0-9]{64}$/u.test(value));
	return value;
}
function allocationPerformers(value, identifier) {
	check(Array.isArray(value) && value.length >= 1 && value.length <= 32);
	const ids = value.map(identifier);
	check(new Set(ids).size === ids.length);
	return Object.freeze(ids);
}
function manualPointShares(value, performers) {
	check(Array.isArray(value) && value.length === performers.length);
	const seen = /* @__PURE__ */ new Set();
	return Object.freeze(value.map((raw) => {
		check(raw !== null && typeof raw === "object" && !Array.isArray(raw) && Object.keys(raw).length === 2 && Object.hasOwn(raw, "member_id") && Object.hasOwn(raw, "amount_minor"));
		const { member_id, amount_minor } = raw;
		check(performers.includes(member_id) && !seen.has(member_id) && Number.isInteger(amount_minor) && amount_minor >= 0 && amount_minor <= 1e6);
		seen.add(member_id);
		return Object.freeze({
			member_id,
			amount_minor
		});
	}));
}
// Edge.57 source: frontend/src/domain/tasks.ts
/** Pure task intents preserve original user data; validation never grants authority. */
var TASK_TEXT_LIMITS = Object.freeze({
	title: 160,
	description: 4e3,
	reason: 1e3
});
var TaskInputError = class extends Error {
	constructor() {
		super("invalid_task_input");
		this.name = "TaskInputError";
	}
};
function requireValue$1(condition) {
	if (!condition) throw new TaskInputError();
}
function taskIdentifier(value) {
	requireValue$1(typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value));
	return value;
}
function hasTaskText(value) {
	return /\P{White_Space}/u.test(value);
}
function taskText(value, maximum, required, multiline = false) {
	requireValue$1(typeof value === "string" && Array.from(value).length <= maximum && (!required || hasTaskText(value)) && !/[\uD800-\uDFFF\u007F]/u.test(value) && !(multiline ? /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/u : /[\u0000-\u001F]/u).test(value));
	return value;
}
function taskTime(value) {
	requireValue$1(typeof value === "string" && value.length <= 19 && /^(?:0|[1-9][0-9]*)$/u.test(value) && BigInt(value) <= 9223372036854775807n);
	return value;
}
function taskQuantity(value) {
	requireValue$1(typeof value === "string" && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$/u.test(value));
	return value;
}
function taskBasePointAmount(value) {
	requireValue$1(typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 1e6);
	return value;
}
function taskAssignees(value) {
	requireValue$1(Array.isArray(value) && value.length <= 32);
	const ids = Array.from(value, taskIdentifier);
	requireValue$1(new Set(ids).size === ids.length);
	return Object.freeze(ids);
}
var TASK_PROGRESS_TARGETS = [
	"in_progress",
	"blocked",
	"assigned",
	"available"
];
var TASK_PRIORITIES = [
	"low",
	"normal",
	"high",
	"urgent"
];
var CATEGORY_ACTIONS = [
	"task.category.create",
	"task.category.rename",
	"task.category.archive"
];
function isCategoryCommand(command) {
	return CATEGORY_ACTIONS.includes(command.action);
}
function categoryLabel(value) {
	requireValue$1(typeof value === "string" && Array.from(value).length <= 256 && !/[\p{Cc}\p{Cs}]/u.test(value));
	const label = value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "").normalize("NFC");
	requireValue$1(label.length > 0 && Array.from(label).length <= 80);
	return label;
}
function fields(value, keys) {
	requireValue$1(typeof value === "object" && value !== null && !Array.isArray(value) && keys.every((key) => Object.hasOwn(value, key)) && Object.keys(value).length === keys.length);
	return value;
}
function choice(value, options) {
	requireValue$1(typeof value === "string" && options.includes(value));
	return value;
}
function taskSchedulePolicy(value) {
	const body = fields(value, [
		"zone",
		"data_identity",
		"repeated_time",
		"revision"
	]);
	const { zone, data_identity } = body;
	requireValue$1(typeof zone === "string" && /^[A-Za-z0-9_+/-]{1,128}$/u.test(zone));
	requireValue$1(typeof data_identity === "string" && /^[A-Za-z0-9:/_.-]{1,128}$/u.test(data_identity));
	return Object.freeze({
		zone,
		data_identity,
		repeated_time: choice(body.repeated_time, ["first_instant", "second_instant"]),
		revision: revisionValue(body.revision)
	});
}
function taskScheduleDraft(value) {
	const kind = choice(value?.kind, ["fixed", "relative"]);
	const body = fields(value, kind === "fixed" ? [
		"kind",
		"start",
		"rrule"
	] : [
		"kind",
		"start",
		"interval_days",
		"visibility"
	]);
	const date = fields(body.start, ["kind", "local"]);
	const startKind = choice(date.kind, ["date", "time"]), local = date.local;
	requireValue$1(typeof local === "string" && (startKind === "date" ? civilDate(local) : civilDate(local.slice(0, 10)) && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/u.test(local)));
	const start = Object.freeze({
		kind: startKind,
		local
	});
	if (kind === "fixed") return Object.freeze({
		kind,
		start,
		rrule: taskText(body.rrule, 2048, true)
	});
	const interval = body.interval_days;
	requireValue$1(typeof interval === "number" && Number.isInteger(interval) && interval >= 1 && interval <= 36600);
	return Object.freeze({
		kind,
		start,
		interval_days: interval,
		visibility: choice(body.visibility, ["at_completion", "at_verification"])
	});
}
function usages(value) {
	if (value === null) return null;
	requireValue$1(Array.isArray(value) && value.length <= 32);
	const seen = /* @__PURE__ */ new Set();
	return Object.freeze(value.map((raw) => {
		const item = fields(raw, ["line_id", "quantity"]), line_id = taskIdentifier(item.line_id);
		requireValue$1(!seen.has(line_id));
		seen.add(line_id);
		return Object.freeze({
			line_id,
			quantity: taskQuantity(item.quantity)
		});
	}));
}
/** Invalid or open-ended data cannot become a network command. No normalization replaces the original. */
function taskCommand(value) {
	try {
		requireValue$1(typeof value === "object" && value !== null && !Array.isArray(value));
		const action = value.action;
		if (action === "task.category.create" || action === "task.category.rename" || action === "task.category.archive") {
			const item = fields(value, action === "task.category.create" ? ["action", "payload"] : [
				"action",
				"categoryId",
				"payload"
			]);
			const body = fields(item.payload, action === "task.category.archive" ? ["expected_revision"] : ["expected_revision", "label"]);
			if (action === "task.category.archive") return Object.freeze({
				action,
				categoryId: taskIdentifier(item.categoryId),
				payload: Object.freeze({ expected_revision: revisionValue(body.expected_revision) })
			});
			categoryLabel(body.label);
			const label = body.label;
			if (action === "task.category.create") {
				requireValue$1(body.expected_revision === 0);
				return Object.freeze({
					action,
					payload: Object.freeze({
						expected_revision: 0,
						label
					})
				});
			}
			return Object.freeze({
				action,
				categoryId: taskIdentifier(item.categoryId),
				payload: Object.freeze({
					expected_revision: revisionValue(body.expected_revision),
					label
				})
			});
		}
		const item = fields(value, action === "task.create" ? ["action", "payload"] : [
			"action",
			"occurrenceId",
			"payload"
		]);
		if (action === "task.create") {
			requireValue$1(typeof item.payload === "object" && item.payload !== null);
			const hasSchedule = Object.hasOwn(item.payload, "schedule");
			const hasCategory = Object.hasOwn(item.payload, "category_id");
			const hasOverrides = Object.hasOwn(item.payload, "overrides");
			const body = fields(item.payload, [
				"expected_revision",
				"title",
				"description",
				"priority",
				...hasSchedule ? ["schedule"] : [],
				...hasCategory ? ["category_id"] : [],
				...hasOverrides ? ["overrides"] : []
			]);
			requireValue$1(body.expected_revision === 0);
			const schedule = hasSchedule ? fields(body.schedule, ["draft", "policy"]) : null;
			let overrides;
			if (hasOverrides) {
				const { point_value_minor } = fields(body.overrides, ["point_value_minor"]);
				overrides = Object.freeze({ point_value_minor: taskBasePointAmount(point_value_minor) });
			}
			return Object.freeze({
				action,
				payload: Object.freeze({
					expected_revision: 0,
					title: taskText(body.title, TASK_TEXT_LIMITS.title, true),
					description: taskText(body.description, TASK_TEXT_LIMITS.description, false, true),
					priority: choice(body.priority, TASK_PRIORITIES),
					...overrides === void 0 ? {} : { overrides },
					...hasCategory ? { category_id: taskIdentifier(body.category_id) } : {},
					...schedule === null ? {} : { schedule: Object.freeze({
						draft: taskScheduleDraft(schedule.draft),
						policy: taskSchedulePolicy(schedule.policy)
					}) }
				})
			});
		}
		const occurrenceId = taskIdentifier(item.occurrenceId);
		if (action === "task.assign") {
			const body = fields(item.payload, ["expected_revision", "assignee_ids"]);
			return Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze({
					expected_revision: revisionValue(body.expected_revision),
					assignee_ids: taskAssignees(body.assignee_ids)
				})
			});
		}
		if (action === "task.transition") {
			const body = fields(item.payload, [
				"expected_revision",
				"target",
				"reason"
			]);
			const target = choice(body.target, TASK_PROGRESS_TARGETS);
			const reason = taskText(body.reason, TASK_TEXT_LIMITS.reason, target === "blocked", true);
			requireValue$1(target === "blocked" || reason === "");
			return Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze({
					expected_revision: revisionValue(body.expected_revision),
					target,
					reason
				})
			});
		}
		if (action === "task.claim") {
			const body = fields(item.payload, ["expected_revision"]);
			return Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze({ expected_revision: revisionValue(body.expected_revision) })
			});
		}
		if (action === "task.complete") {
			requireValue$1(typeof item.payload === "object" && item.payload !== null);
			const base = item.payload;
			const hasFingerprint = Object.hasOwn(base, "allocation_fingerprint"), hasManual = Object.hasOwn(base, "manual_shares");
			const body = fields(base, [
				"expected_revision",
				"performer_ids",
				"performed_at",
				"material_usages",
				...hasFingerprint ? ["allocation_fingerprint"] : [],
				...hasManual ? ["manual_shares"] : []
			]);
			const performer_ids = allocationPerformers(body.performer_ids, taskIdentifier);
			return Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze({
					expected_revision: revisionValue(body.expected_revision),
					performer_ids,
					performed_at: taskTime(body.performed_at),
					material_usages: usages(body.material_usages),
					...hasFingerprint ? { allocation_fingerprint: allocationFingerprint(body.allocation_fingerprint) } : {},
					...hasManual ? { manual_shares: manualPointShares(body.manual_shares, performer_ids) } : {}
				})
			});
		}
		if (action === "task.verify" || action === "task.reopen") {
			const body = fields(item.payload, action === "task.verify" ? [
				"expected_revision",
				"cycle_id",
				"decision",
				"reason"
			] : [
				"expected_revision",
				"cycle_id",
				"reason"
			]);
			const payload = {
				expected_revision: revisionValue(body.expected_revision),
				cycle_id: taskIdentifier(body.cycle_id),
				reason: taskText(body.reason, TASK_TEXT_LIMITS.reason, action === "task.reopen" || body.decision === "rejected", true)
			};
			return action === "task.verify" ? Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze({
					...payload,
					decision: choice(body.decision, ["approved", "rejected"])
				})
			}) : Object.freeze({
				action,
				occurrenceId,
				payload: Object.freeze(payload)
			});
		}
		throw new TaskInputError();
	} catch {
		return;
	}
}
// Edge.57 source: frontend/src/adapters/task-journal.ts
/** One owned session-storage key retains bounded original task requests, never credentials. */
var TASK_JOURNAL_KEY = "domus.tasks.journal.v1";
function requireValue(condition) {
	if (!condition) throw new JournalError("invalid_journal");
}
function object(value, keys) {
	requireValue(typeof value === "object" && value !== null && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key)));
	return value;
}
function time(value) {
	if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new JournalError("invalid_journal_time");
	return value;
}
function scope$1(value) {
	const item = object(value, [
		"context",
		"householdId",
		"memberId"
	]);
	return Object.freeze({
		context: emptyJournal(item.context, 0).context,
		householdId: taskIdentifier(item.householdId),
		memberId: taskIdentifier(item.memberId)
	});
}
function taskScopeKey(value) {
	const selected = scope$1(value);
	return JSON.stringify([
		selected.context.installationId,
		selected.context.channel,
		selected.context.subject,
		selected.householdId,
		selected.memberId
	]);
}
function record(value, observedAt) {
	const item = object(value, [
		"key",
		"command",
		"scope",
		"createdAt",
		"expiresAt",
		"stage",
		"operationId"
	]);
	const command = taskCommand(item.command);
	requireValue(command !== void 0);
	const createdAt = time(item.createdAt), expiresAt = time(item.expiresAt);
	if (createdAt > observedAt || expiresAt !== createdAt + 36e5) throw new JournalError("invalid_journal_time");
	requireValue([
		"prepared",
		"uncertain",
		"committed",
		"historical",
		"rejected"
	].includes(item.stage));
	const known = item.stage === "committed" || item.stage === "historical";
	const operationId = known ? taskIdentifier(item.operationId) : null;
	requireValue(known || item.operationId === null);
	return Object.freeze({
		key: taskIdentifier(item.key),
		command,
		scope: scope$1(item.scope),
		createdAt,
		expiresAt,
		stage: item.stage,
		operationId
	});
}
function snapshot(now, records) {
	return Object.freeze({
		namespace: "tasks",
		version: 1,
		observedAt: time(now),
		records: Object.freeze(records)
	});
}
function inspect(value, now) {
	const item = object(value, [
		"namespace",
		"version",
		"observedAt",
		"records"
	]);
	requireValue(item.namespace === "tasks" && item.version === 1);
	const observedAt = time(item.observedAt);
	if (time(now) < observedAt) throw new JournalError("invalid_journal_time");
	requireValue(Array.isArray(item.records) && item.records.length <= 8);
	const records = item.records.map((raw) => record(raw, observedAt));
	const identities = records.map((item) => JSON.stringify([taskScopeKey(item.scope), item.key]));
	if (new Set(identities).size !== records.length) throw new JournalError("duplicate_request");
	return snapshot(now, records.filter((item) => now < item.expiresAt));
}
function decode(raw) {
	if (raw.length > 65536 || new TextEncoder().encode(raw).byteLength > 65536) throw new JournalError("journal_too_large");
	try {
		const value = JSON.parse(raw);
		requireValue(JSON.stringify(value) === raw);
		return value;
	} catch {
		throw new JournalError("invalid_journal");
	}
}
var TaskSessionJournal = class {
	storage;
	active = null;
	constructor(storage) {
		this.storage = storage;
	}
	read() {
		try {
			if (this.storage === void 0) throw Error();
			const raw = this.storage.getItem(TASK_JOURNAL_KEY);
			if (raw !== null && typeof raw !== "string") throw Error();
			return raw;
		} catch {
			throw new JournalStorageError("storage_unavailable");
		}
	}
	persist(expected, state, selected) {
		this.active = null;
		if (this.read() !== expected) throw new JournalStorageError("storage_changed");
		const encoded = JSON.stringify(state);
		decode(encoded);
		try {
			this.storage.setItem(TASK_JOURNAL_KEY, encoded);
		} catch {
			throw new JournalStorageError("storage_unavailable");
		}
		if (this.read() !== encoded) throw new JournalStorageError("storage_unconfirmed");
		this.active = {
			scope: selected,
			state,
			encoded
		};
		const key = taskScopeKey(selected);
		return Object.freeze(state.records.filter((item) => taskScopeKey(item.scope) === key));
	}
	open(value, now) {
		this.active = null;
		const selected = scope$1(value), raw = this.read();
		return this.persist(raw, raw === null ? snapshot(now, []) : inspect(decode(raw), now), selected);
	}
	change(now, update) {
		const prior = this.active;
		this.active = null;
		if (prior === null) throw new JournalStorageError("journal_not_open");
		return this.persist(prior.encoded, snapshot(now, update(inspect(prior.state, now), prior.scope)), prior.scope);
	}
	prepare(key, command, now) {
		return this.change(now, (state, selected) => {
			if (state.records.length >= 8) throw new JournalError("journal_capacity");
			if (state.records.some((item) => taskScopeKey(item.scope) === taskScopeKey(selected) && item.key === key)) throw new JournalError("duplicate_request");
			return [...state.records, record({
				key,
				command,
				scope: selected,
				createdAt: now,
				expiresAt: now + JOURNAL_LIFETIME,
				stage: "prepared",
				operationId: null
			}, now)];
		});
	}
	target(state, selected, key) {
		const original = state.records.find((item) => taskScopeKey(item.scope) === taskScopeKey(selected) && item.key === key);
		if (!original) throw new JournalError("request_not_found");
		return original;
	}
	record(key, stage, operationId, now) {
		return this.change(now, (state, selected) => {
			const original = this.target(state, selected, key);
			requireValue(stage !== "prepared");
			const next = record({
				...original,
				stage,
				operationId
			}, now);
			if (original.operationId !== null && original.operationId !== next.operationId) throw new JournalError("original_operation_changed");
			return state.records.map((item) => item === original ? next : item);
		});
	}
	forget(key, now) {
		return this.change(now, (state, selected) => {
			const original = this.target(state, selected, key);
			if (original.stage === "prepared" || original.stage === "uncertain") throw new JournalError("unresolved_request");
			return state.records.filter((item) => item !== original);
		});
	}
	detach() {
		this.active = null;
	}
};
// Edge.57 source: frontend/src/application/task-controller.ts
/** Task workflows coordinate current identity, durable original intents and server-owned actions. */
function blank(phase) {
	return Object.freeze({
		phase,
		session: null,
		access: null,
		scopeKey: null,
		readOnly: true,
		page: null,
		detail: null,
		records: null,
		outcome: null,
		notice: null
	});
}
function scope(session, access) {
	return Object.freeze({
		context: session.context,
		householdId: access.householdId,
		memberId: access.memberId
	});
}
function scopeKey(selected) {
	const { context } = selected;
	return JSON.stringify([
		context.installationId,
		context.channel,
		context.subject,
		selected.householdId,
		selected.memberId
	]);
}
var retired = Symbol("retired task request");
var TaskController = class {
	deployment;
	identity;
	server;
	journal;
	clock;
	entropy;
	state = blank("idle");
	generation = 0;
	running = false;
	closed = false;
	reads = /* @__PURE__ */ new Set();
	constructor(deployment, identity, server, journal, clock, entropy) {
		this.deployment = deployment;
		this.identity = identity;
		this.server = server;
		this.journal = journal;
		this.clock = clock;
		this.entropy = entropy;
	}
	get view() {
		return Object.freeze({
			...this.state,
			busy: this.running
		});
	}
	update(patch) {
		this.state = Object.freeze({
			...this.state,
			...patch
		});
	}
	invalidate() {
		this.generation++;
		const owned = [...this.reads];
		this.reads.clear();
		for (const read of owned) try {
			read.cancel();
		} catch {}
		this.journal.detach();
		return this.generation;
	}
	async read(operation, generation) {
		this.reads.add(operation);
		try {
			const value = await operation.result;
			if (this.closed || generation !== this.generation) throw retired;
			if (this.state.session !== null && this.clock.now() >= this.state.session.expiresAt) throw new EntryReadError("authentication_required");
			return value;
		} finally {
			this.reads.delete(operation);
		}
	}
	async fresh(generation) {
		const source = await this.read(this.identity.session(), generation);
		if (source === null) throw new EntryReadError("authentication_required");
		if (source.deployment !== this.deployment) throw new EntryReadError("invalid_response");
		this.clock.anchor(source.serverTime);
		if (this.clock.now() >= source.expiresAt) throw new EntryReadError("authentication_required");
		if (!source.householdApiAvailable) throw new EntryReadError("unavailable");
		const session = Object.freeze({
			...source,
			context: Object.freeze({ ...source.context })
		});
		this.update({
			session,
			readOnly: source.access !== "full"
		});
		const current = await this.read(this.server.access(session.context), generation);
		const access = Object.freeze({ ...current }), selected = scope(session, access);
		let records = null;
		try {
			records = this.journal.open(selected, this.clock.now());
		} catch {}
		this.update({
			access,
			scopeKey: scopeKey(selected),
			records,
			notice: records === null ? "journal_unavailable" : null
		});
	}
	async run(work) {
		if (this.closed || this.running) return;
		const prior = this.state, generation = this.invalidate();
		this.running = true;
		this.state = blank("loading");
		try {
			await this.fresh(generation);
			await work(prior, generation);
		} catch (error) {
			if (generation !== this.generation || this.closed || error === retired) return;
			const notice = error instanceof EntryReadError ? error.code : "unavailable";
			if (notice === "authentication_required" || notice === "forbidden") this.state = Object.freeze({
				...blank("ready"),
				notice
			});
			else this.update({ notice });
		} finally {
			if (generation === this.generation && !this.closed) {
				this.running = false;
				this.update({ phase: "ready" });
			}
		}
	}
	async facts(generation, selected, cursor = null) {
		const session = this.state.session, access = this.state.access;
		const page = await this.read(this.server.list(session.context, cursor), generation);
		this.update({ page });
		if (selected !== null) this.update({ detail: await this.read(this.server.detail(selected, access.householdId, session.context), generation) });
	}
	refresh() {
		return this.run(async (prior, generation) => {
			const same = this.state.scopeKey === prior.scopeKey;
			if (same) this.update({ outcome: prior.outcome });
			await this.facts(generation, same ? prior.detail?.occurrenceId ?? null : null);
		});
	}
	more() {
		const cursor = this.state.page?.nextCursor;
		if (!cursor) return Promise.resolve();
		return this.run(async (prior, generation) => {
			if (this.state.scopeKey !== prior.scopeKey) {
				this.update({ notice: "context_changed" });
				return;
			}
			await this.facts(generation, null, cursor);
		});
	}
	select(value) {
		let id;
		try {
			id = taskIdentifier(value);
		} catch {
			this.update({ notice: "invalid_input" });
			return Promise.resolve();
		}
		return this.run(async (prior, generation) => {
			if (this.state.scopeKey !== prior.scopeKey) {
				this.update({ notice: "context_changed" });
				return;
			}
			const detail = await this.read(this.server.detail(id, this.state.access.householdId, this.state.session.context), generation);
			this.update({
				page: prior.page,
				detail,
				outcome: prior.outcome
			});
		});
	}
	accepted(command) {
		const access = this.state.access;
		if (command.action === "task.create") {
			if (command.payload.category_id !== void 0 && !access.categoryCatalog?.categories.some((item) => item.id === command.payload.category_id)) {
				this.update({ notice: "category_unavailable" });
				return false;
			}
			return access.canCreate && (command.payload.overrides === void 0 || access.canConfigure === true);
		}
		if (isCategoryCommand(command)) {
			if (!access.categoryCatalog?.canManage) return false;
			if (command.action === "task.category.create") return true;
			if (access.categoryCatalog.categories.find((item) => item.id === command.categoryId)?.revision !== command.payload.expected_revision) {
				this.update({ notice: "conflict" });
				return false;
			}
			return true;
		}
		const detail = this.state.detail;
		if (detail.occurrenceId !== command.occurrenceId) return false;
		if (detail.revision !== command.payload.expected_revision) {
			this.update({ notice: "conflict" });
			return false;
		}
		if (command.action === "task.transition") return detail.allowedActions.includes("transition:" + command.payload.target);
		const action = command.action === "task.verify" ? command.payload.decision === "approved" ? "approve" : "reject" : command.action.slice(5);
		return detail.allowedActions.includes(action);
	}
	save(key, outcome) {
		const stage = outcome.kind === "receipt" ? outcome.stage : outcome.kind;
		try {
			this.update({ records: this.journal.record(key, stage, outcome.kind === "receipt" ? outcome.operationId : null, this.clock.now()) });
		} catch {
			this.update({ notice: "journal_unavailable" });
		}
		this.update({ outcome });
	}
	execute(value) {
		if (this.closed || this.running || this.state.access === null) return Promise.resolve();
		const command = taskCommand(value);
		if (command === void 0) {
			this.update({ notice: "invalid_input" });
			return Promise.resolve();
		}
		return this.run(async (prior, generation) => {
			if (this.state.scopeKey !== prior.scopeKey) {
				this.update({ notice: "context_changed" });
				return;
			}
			this.update({ page: prior.page });
			if (this.state.readOnly) {
				this.update({ notice: "read_only" });
				return;
			}
			if ("occurrenceId" in command) this.update({ detail: await this.read(this.server.detail(command.occurrenceId, this.state.access.householdId, this.state.session.context), generation) });
			if (!this.accepted(command)) {
				if (this.state.notice !== "conflict" && this.state.notice !== "category_unavailable") this.update({ notice: "action_not_allowed" });
				if (command.action === "task.transition") {
					this.update({ page: null });
					await this.facts(generation, command.occurrenceId);
				}
				return;
			}
			if (this.state.records === null) {
				this.update({ notice: "journal_unavailable" });
				return;
			}
			if (this.state.records.some((item) => item.stage === "prepared" || item.stage === "uncertain")) {
				this.update({ notice: "previous_request_unresolved" });
				return;
			}
			let key;
			try {
				key = this.entropy.requestKey();
				this.update({ records: this.journal.prepare(key, command, this.clock.now()) });
			} catch (error) {
				this.update({ notice: error instanceof JournalError && (error.code === "journal_capacity" || error.code === "journal_too_large") ? "journal_capacity" : "journal_unavailable" });
				return;
			}
			const outcome = await this.server.send({
				key,
				command
			}, this.state.session.context);
			if (this.closed || generation !== this.generation) return;
			this.save(key, outcome);
			if (outcome.kind === "rejected" && (outcome.reason === "authentication_required" || outcome.reason === "forbidden")) {
				this.state = Object.freeze({
					...blank("ready"),
					notice: outcome.reason
				});
				return;
			}
			if (this.clock.now() >= this.state.session.expiresAt) throw new EntryReadError("authentication_required");
			if (outcome.kind === "receipt") await this.receiptFacts(command, outcome.occurrenceId, prior, generation);
			if ((command.action === "task.assign" || command.action === "task.transition") && outcome.kind === "rejected" && outcome.reason === "conflict") await this.facts(generation, command.occurrenceId);
		});
	}
	async receiptFacts(command, occurrence, prior, generation) {
		if (isCategoryCommand(command)) {
			const current = await this.read(this.server.access(this.state.session.context), generation);
			if (scopeKey(scope(this.state.session, current)) !== prior.scopeKey) {
				this.journal.detach();
				this.state = Object.freeze({
					...blank("ready"),
					notice: "context_changed"
				});
				return;
			}
			this.update({ access: Object.freeze({ ...current }) });
			await this.facts(generation, prior.detail?.occurrenceId ?? null);
			return;
		}
		await this.facts(generation, occurrence);
	}
	create(title, description, priority, draft, categoryId, basePointsMinor) {
		const schedule = draft === void 0 ? {} : { schedule: {
			draft,
			policy: this.state.access?.schedulePolicy
		} };
		return this.execute({
			action: "task.create",
			payload: {
				expected_revision: 0,
				title,
				description,
				priority,
				...schedule,
				...categoryId === void 0 ? {} : { category_id: categoryId },
				...basePointsMinor === void 0 ? {} : { overrides: { point_value_minor: basePointsMinor } }
			}
		});
	}
	createCategory(label) {
		return this.execute({
			action: "task.category.create",
			payload: {
				expected_revision: 0,
				label
			}
		});
	}
	renameCategory(categoryId, revision, label) {
		return this.execute({
			action: "task.category.rename",
			categoryId,
			payload: {
				expected_revision: revision,
				label
			}
		});
	}
	archiveCategory(categoryId, revision) {
		return this.execute({
			action: "task.category.archive",
			categoryId,
			payload: { expected_revision: revision }
		});
	}
	claim() {
		const work = this.state.detail;
		return work === null ? Promise.resolve() : this.execute({
			action: "task.claim",
			occurrenceId: work.occurrenceId,
			payload: { expected_revision: work.revision }
		});
	}
	assign(occurrenceId, revision, assigneeIds) {
		const work = this.state.detail;
		if (work === null) return Promise.resolve();
		if (work.occurrenceId !== occurrenceId) {
			this.update({ notice: "conflict" });
			return Promise.resolve();
		}
		return this.execute({
			action: "task.assign",
			occurrenceId,
			payload: {
				expected_revision: revision,
				assignee_ids: assigneeIds
			}
		});
	}
	transition(occurrenceId, revision, target, reason) {
		const work = this.state.detail;
		if (work === null) return Promise.resolve();
		if (work.occurrenceId !== occurrenceId) {
			this.update({ notice: "conflict" });
			return Promise.resolve();
		}
		return this.execute({
			action: "task.transition",
			occurrenceId,
			payload: {
				expected_revision: revision,
				target,
				reason
			}
		});
	}
	complete(materialUsages, reviewed) {
		const work = this.state.detail, member = this.state.access?.memberId;
		if (work === null || member === void 0) return Promise.resolve();
		if (reviewed !== void 0 && (reviewed.occurrenceId !== work.occurrenceId || reviewed.revision !== work.revision)) {
			this.update({ notice: "conflict" });
			return Promise.resolve();
		}
		let performedAt;
		try {
			performedAt = String(this.clock.now());
		} catch {
			this.update({ notice: "unavailable" });
			return Promise.resolve();
		}
		return this.execute({
			action: "task.complete",
			occurrenceId: work.occurrenceId,
			payload: {
				expected_revision: work.revision,
				performer_ids: reviewed?.performerIds ?? [member],
				performed_at: performedAt,
				material_usages: materialUsages,
				...reviewed === void 0 ? {} : { allocation_fingerprint: reviewed.fingerprint },
				...reviewed?.manualShares === void 0 ? {} : { manual_shares: reviewed.manualShares }
			}
		});
	}
	verify(decision, reason) {
		const work = this.state.detail;
		return work?.cycle == null ? Promise.resolve() : this.execute({
			action: "task.verify",
			occurrenceId: work.occurrenceId,
			payload: {
				expected_revision: work.revision,
				cycle_id: work.cycle.cycleId,
				decision,
				reason
			}
		});
	}
	reopen(reason) {
		const work = this.state.detail;
		return work?.cycle == null ? Promise.resolve() : this.execute({
			action: "task.reopen",
			occurrenceId: work.occurrenceId,
			payload: {
				expected_revision: work.revision,
				cycle_id: work.cycle.cycleId,
				reason
			}
		});
	}
	recover(key) {
		const original = this.state.records?.find((item) => item.key === key);
		if (!original) return Promise.resolve();
		return this.run(async (prior, generation) => {
			if (this.state.scopeKey !== prior.scopeKey) {
				this.update({ notice: "context_changed" });
				return;
			}
			const current = this.state.records?.find((item) => item.key === key);
			if (current === void 0 || JSON.stringify(current) !== JSON.stringify(original)) {
				this.update({ notice: "request_changed" });
				return;
			}
			this.update({ page: prior.page });
			const outcome = await this.read(this.server.original({
				key,
				command: current.command,
				operationId: current.operationId
			}, this.state.session.context), generation);
			this.save(key, outcome);
			await this.receiptFacts(current.command, outcome.occurrenceId, prior, generation);
		});
	}
	dismiss(key) {
		return this.run(async (prior) => {
			if (this.state.scopeKey !== prior.scopeKey) {
				this.update({ notice: "context_changed" });
				return;
			}
			try {
				this.update({
					records: this.journal.forget(key, this.clock.now()),
					page: prior.page,
					detail: prior.detail
				});
			} catch {
				this.update({ notice: "request_unavailable" });
			}
		});
	}
	tick() {
		if (this.closed || this.state.session === null) return;
		try {
			const now = this.clock.now();
			if (now < this.state.session.expiresAt) {
				if (this.state.records?.some((record) => now >= record.expiresAt)) try {
					this.update({ records: this.journal.open(scope(this.state.session, this.state.access), now) });
				} catch {
					this.journal.detach();
					this.update({
						records: null,
						notice: "journal_unavailable"
					});
				}
				return;
			}
		} catch {}
		this.invalidate();
		this.running = false;
		this.state = Object.freeze({
			...blank("ready"),
			notice: "authentication_required"
		});
	}
	close() {
		this.closed = true;
		this.invalidate();
		this.running = false;
		this.state = blank("closed");
	}
};
export { TASK_JOURNAL_KEY, TaskController, TaskSessionJournal };
