// edge72/frontend/src/domain/administration.ts
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
Object.freeze({
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
function requireValue(condition) {
	if (!condition) throw new TaskInputError();
}
function taskIdentifier(value) {
	requireValue(typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value));
	return value;
}
function hasTaskText(value) {
	return /\P{White_Space}/u.test(value);
}
function taskText(value, maximum, required, multiline = false) {
	requireValue(typeof value === "string" && Array.from(value).length <= maximum && (!required || hasTaskText(value)) && !/[\uD800-\uDFFF\u007F]/u.test(value) && !(multiline ? /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/u : /[\u0000-\u001F]/u).test(value));
	return value;
}
function taskQuantity(value) {
	requireValue(typeof value === "string" && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,5}[1-9])?$/u.test(value));
	return value;
}
// edge72/frontend/src/domain/inventory.ts
/** Catalog commands and exact base-unit quantities shared by the protected workspace. */
var BASE_UNITS = [
	"piece",
	"gram",
	"millilitre"
];
function canonicalGtin(value) {
	if (typeof value !== "string" || ![
		8,
		12,
		13,
		14
	].includes(value.length) || /[^0-9]/u.test(value)) throw new Error("invalid_inventory_barcode");
	let total = Number(value[value.length - 1]);
	for (const [index, digit] of [...value.slice(0, -1)].reverse().entries()) total += Number(digit) * (index % 2 === 0 ? 3 : 1);
	if (total % 10 !== 0) throw new Error("invalid_inventory_barcode");
	return value.padStart(14, "0");
}
function shoppingItemKey(item) {
	return item.productId === null ? "extra:" + item.extraId : "product:" + item.productId;
}
function hasFields(record, fields) {
	return Object.keys(record).length === fields.length && fields.every((key) => Object.hasOwn(record, key));
}
function locationName(value) {
	const name = taskText(value, 80, true);
	if (name !== name.trim() || ["pantry", "despensa"].includes(name.toLowerCase())) throw new Error("invalid_inventory_location_name");
	return name;
}
function purchaseStoreName(value) {
	return taskText(value, 160, true);
}
function positiveQuantity(value) {
	const quantity = taskQuantity(value);
	if (quantity === "0") throw new Error("invalid_inventory_quantity");
	return quantity;
}
function sessionSelection(value) {
	if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_inventory_command");
	const item = value;
	if (!hasFields(item, [
		"product_id",
		"extra_id",
		"quantity"
	]) || item.product_id === null === (item.extra_id === null)) throw new Error("invalid_inventory_command");
	return {
		product_id: item.product_id === null ? null : taskIdentifier(item.product_id),
		extra_id: item.extra_id === null ? null : taskIdentifier(item.extra_id),
		quantity: positiveQuantity(item.quantity)
	};
}
function inventoryCommand(value) {
	if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_inventory_command");
	const record = value;
	const { action } = record;
	if (action === "inventory.link-barcode" && hasFields(record, [
		"action",
		"barcode",
		"product_id"
	])) return {
		action,
		barcode: canonicalGtin(record.barcode),
		product_id: taskIdentifier(record.product_id)
	};
	if (action === "inventory.remove-barcode" && hasFields(record, [
		"action",
		"barcode",
		"product_id",
		"association_id"
	])) return {
		action,
		barcode: canonicalGtin(record.barcode),
		product_id: taskIdentifier(record.product_id),
		association_id: taskIdentifier(record.association_id)
	};
	if (action === "inventory.add-location" && hasFields(record, ["action", "name"])) return {
		action,
		name: locationName(record.name)
	};
	if (action === "inventory.transfer" && hasFields(record, [
		"action",
		"product_id",
		"source_location",
		"destination_location",
		"quantity"
	])) {
		const source_location = taskIdentifier(record.source_location);
		const destination_location = taskIdentifier(record.destination_location);
		if (source_location !== destination_location) return {
			action,
			product_id: taskIdentifier(record.product_id),
			source_location,
			destination_location,
			quantity: positiveQuantity(record.quantity)
		};
	}
	if (Object.keys(record).length === 3 && Object.hasOwn(record, "action")) {
		if (action === "inventory.register-product" && Object.hasOwn(record, "name") && Object.hasOwn(record, "base_unit")) {
			const base_unit = record.base_unit;
			if (BASE_UNITS.includes(base_unit)) return {
				action,
				name: taskText(record.name, 160, true),
				base_unit
			};
		}
		if (action === "inventory.intake" && Object.hasOwn(record, "product_id") && Object.hasOwn(record, "quantity")) {
			const quantity = taskQuantity(record.quantity);
			if (quantity !== "0") return {
				action,
				product_id: taskIdentifier(record.product_id),
				quantity
			};
		}
	}
	if (Object.keys(record).length === 4 && Object.hasOwn(record, "action") && Object.hasOwn(record, "product_id") && Object.hasOwn(record, "reason")) {
		if (action === "inventory.adjust" && Object.hasOwn(record, "quantity")) return {
			action,
			product_id: taskIdentifier(record.product_id),
			quantity: signedQuantity(record.quantity),
			reason: taskText(record.reason, 240, true)
		};
		if (action === "inventory.correct-intake" && Object.hasOwn(record, "movement_id")) return {
			action,
			product_id: taskIdentifier(record.product_id),
			movement_id: taskIdentifier(record.movement_id),
			reason: taskText(record.reason, 240, true)
		};
	}
	const policyKeys = [
		"action",
		"product_id",
		"minimum",
		"target",
		"expected_revision"
	];
	if (action === "inventory.configure-replenishment" && Object.keys(record).length === policyKeys.length && policyKeys.every((key) => Object.hasOwn(record, key))) return {
		action,
		product_id: taskIdentifier(record.product_id),
		minimum: taskQuantity(record.minimum),
		target: taskQuantity(record.target),
		expected_revision: replenishmentRevision(record.expected_revision)
	};
	if ((action === "shopping.purchase" || action === "shopping.add-extra") && hasFields(record, [
		"action",
		"product_id",
		"name",
		"quantity"
	])) {
		const product_id = record.product_id === null ? null : taskIdentifier(record.product_id);
		const name = record.name === null ? null : taskText(record.name, 160, true);
		if (product_id === null !== (name === null)) return {
			action,
			product_id,
			name,
			quantity: positiveQuantity(record.quantity)
		};
	}
	if (action === "shopping.receive" && hasFields(record, [
		"action",
		"purchase_id",
		"quantity",
		"expected_revision"
	])) return {
		action,
		purchase_id: taskIdentifier(record.purchase_id),
		quantity: positiveQuantity(record.quantity),
		expected_revision: revisionValue(record.expected_revision)
	};
	if (action === "shopping.cancel-balance" && hasFields(record, [
		"action",
		"purchase_id",
		"reason",
		"expected_revision"
	])) return {
		action,
		purchase_id: taskIdentifier(record.purchase_id),
		reason: taskText(record.reason, 240, true),
		expected_revision: revisionValue(record.expected_revision)
	};
	if ((action === "shopping.void-receipt" || action === "shopping.correct-posted-receipt" || action === "shopping.return-receipt") && hasFields(record, [
		"action",
		"purchase_id",
		"receipt_id",
		"reason",
		"expected_revision"
	])) return {
		action,
		purchase_id: taskIdentifier(record.purchase_id),
		receipt_id: taskIdentifier(record.receipt_id),
		reason: taskText(record.reason, 240, true),
		expected_revision: revisionValue(record.expected_revision)
	};
	if (action === "shopping.post-receipt" && hasFields(record, [
		"action",
		"purchase_id",
		"receipt_id"
	])) return {
		action,
		purchase_id: taskIdentifier(record.purchase_id),
		receipt_id: taskIdentifier(record.receipt_id)
	};
	if (action === "shopping.clear-extra" && hasFields(record, ["action", "extra_id"])) return {
		action,
		extra_id: taskIdentifier(record.extra_id)
	};
	if (action === "shopping.record-session" && Array.isArray(record.items) && record.items.length >= 2 && record.items.length <= 16 && (hasFields(record, ["action", "items"]) || hasFields(record, [
		"action",
		"items",
		"store_name"
	]))) {
		const items = record.items.map(sessionSelection);
		if (new Set(items.map((item) => JSON.stringify([item.product_id, item.extra_id]))).size === items.length) return Object.hasOwn(record, "store_name") ? {
			action,
			items,
			store_name: purchaseStoreName(record.store_name)
		} : {
			action,
			items
		};
	}
	throw new Error("invalid_inventory_command");
}
function replenishmentRevision(value) {
	return value === "0" ? value : revisionValue(value);
}
function signedQuantity(value) {
	const negative = typeof value === "string" && value.startsWith("-");
	const amount = taskQuantity(negative ? value.slice(1) : value);
	if (amount === "0") throw new Error("invalid_inventory_quantity");
	return negative ? "-" + amount : amount;
}
// edge72/frontend/src/application/ports.ts
var EntryReadError = class extends Error {
	code;
	constructor(code) {
		super(code);
		this.code = code;
		this.name = "EntryReadError";
	}
};
// edge72/frontend/src/adapters/json-values.ts
/** Shared closed JSON/scalar boundary; original integer sources never round through Number. */
function invalid() {
	throw new EntryReadError("invalid_response");
}
function check(condition) {
	if (!condition) invalid();
}
function fields(value, required, optional) {
	check(typeof value === "object" && value !== null && !Array.isArray(value));
	check(required.every((key) => Object.hasOwn(value, key)) && Object.keys(value).every((key) => required.includes(key) || optional.includes(key)));
	return value;
}
function text(value, maximum) {
	check(typeof value === "string" && value.length > 0 && Array.from(value).length <= maximum && !/[\uD800-\uDFFF]/u.test(value));
	return value;
}
function identifier(value) {
	check(typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value));
	return value;
}
// edge72/frontend/src/adapters/scoped-command-journal.ts
/** Preserve one exact request for its verified scope and retire incompatible browser data. */
var ScopedCommandJournal = class {
	storage;
	key;
	decode;
	constructor(storage, key, decode) {
		this.storage = storage;
		this.key = key;
		this.decode = decode;
	}
	open(scope) {
		const raw = this.storage.getItem(this.key);
		if (raw === null) return null;
		const request = this.decode(raw);
		if (request.scope === scope) return request;
		this.clear(request);
		return null;
	}
	save(request) {
		const raw = JSON.stringify(request);
		this.decode(raw);
		check(this.storage.getItem(this.key) === null);
		this.storage.setItem(this.key, raw);
		check(this.storage.getItem(this.key) === raw);
	}
	clear(request) {
		check(this.storage.getItem(this.key) === JSON.stringify(request));
		this.storage.removeItem(this.key);
		check(this.storage.getItem(this.key) === null);
	}
};
// edge72/frontend/src/adapters/inventory-journal.ts
var INVENTORY_JOURNAL_KEY = "domus.inventory.v1";
function decode(raw) {
	check(raw.length <= 4096);
	const value = fields(JSON.parse(raw), [
		"key",
		"scope",
		"command"
	], []);
	const request = {
		key: identifier(value.key),
		scope: text(value.scope, 1024),
		command: inventoryCommand(value.command)
	};
	check(JSON.stringify(request) === raw);
	return request;
}
var InventorySessionJournal = class extends ScopedCommandJournal {
	constructor(storage) {
		super(storage, INVENTORY_JOURNAL_KEY, decode);
	}
};
// edge72/frontend/src/application/inventory-controller.ts
/** Manage only current household scope and the original unresolved stock command. */
function mayWrite(report, action) {
	if (action === "shopping.correct-posted-receipt" || action === "shopping.return-receipt") return report?.mayManage === true && report.mayShop;
	if (action === "shopping.add-extra") return report?.mayRequest === true;
	if (action === "shopping.purchase" || action === "shopping.receive" || action === "shopping.clear-extra" || action === "shopping.record-session" || action === "shopping.cancel-balance" || action === "shopping.void-receipt") return report?.mayShop === true;
	return report?.mayManage === true;
}
var InventoryController = class {
	server;
	journal;
	entropy;
	publish;
	view = null;
	owned = null;
	request = null;
	constructor(server, journal, entropy, publish) {
		this.server = server;
		this.journal = journal;
		this.entropy = entropy;
		this.publish = publish;
	}
	bind(scope) {
		const previous = this.view?.scope;
		if (scope?.key === previous?.key && scope?.readOnly === previous?.readOnly && scope?.shoppingTarget === previous?.shoppingTarget && scope?.authorityKey === previous?.authorityKey) return;
		this.owned?.cancel();
		this.owned = null;
		this.request = null;
		this.view = scope === null ? null : {
			scope,
			report: null,
			history: null,
			pending: false,
			busy: false,
			result: null,
			notice: null
		};
		this.publish(this.view);
		if (scope === null) return;
		try {
			this.request = this.journal.open(scope.key);
			this.set({ pending: this.request !== null });
		} catch {
			this.set({
				pending: true,
				notice: "unavailable"
			});
		}
		this.refresh();
	}
	async refresh() {
		const state = this.view;
		await this.load(null);
		if (state?.history && this.view?.scope === state.scope && this.view.history) await this.showHistory(state.history.productId);
		if (state?.purchases && this.view?.scope === state.scope && this.view.purchases) await this.showPurchases();
		if (state?.purchaseSessions && this.view?.scope === state.scope && this.view.purchaseSessions) await this.showPurchaseSessions();
		if (state?.purchaseSession && this.view?.scope === state.scope && this.view.purchaseSession) await this.showPurchaseSession(state.purchaseSession.session.id);
		if (state?.purchaseReceipts && this.view?.scope === state.scope && this.view.purchaseReceipts) await this.showPurchaseReceipts(state.purchaseReceipts.purchase.id);
		if (state && this.view?.scope === state.scope && this.view.report) {
			if (state.scope.shoppingTarget) await this.openShoppingItem(state.scope, state.scope.shoppingTarget);
			else if (state.shoppingList) await this.showShoppingList();
		}
		if (state?.shoppingSources && this.view?.scope === state.scope && this.view.shoppingSources) await this.showShoppingSources(state.shoppingSources.item.productId);
		if (state?.barcode && this.view?.scope === state.scope && this.view.report) await this.showBarcode(state.barcode.code);
	}
	async showBarcode(value) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		let code;
		try {
			code = canonicalGtin(value);
		} catch {
			return;
		}
		this.set({ barcode: {
			code,
			lookup: null,
			unavailable: false
		} });
		if (!await this.run(this.server.barcode(state.scope, code), (lookup) => {
			this.set({ barcode: {
				code,
				lookup,
				unavailable: false
			} });
		}, state.pending ? state.notice : null) && this.view?.scope === state.scope && this.view.report !== null) this.set({ barcode: {
			code,
			lookup: null,
			unavailable: true
		} });
	}
	async showHistory(productId) {
		await this.loadHistory(productId, null);
	}
	async moreHistory() {
		const history = this.view?.history;
		if (history?.cursor) await this.loadHistory(history.productId, history.cursor);
	}
	closeHistory() {
		if (this.view && this.owned === null) this.set({ history: null });
	}
	async more() {
		const cursor = this.view?.report?.cursor;
		if (cursor) await this.load(cursor);
	}
	async showPurchases() {
		await this.loadPurchases(null);
	}
	async morePurchases() {
		const cursor = this.view?.purchases?.cursor;
		if (cursor) await this.loadPurchases(cursor);
	}
	async showPurchaseReceipts(purchaseId) {
		await this.loadPurchaseReceipts(purchaseId, null);
	}
	async morePurchaseReceipts() {
		const page = this.view?.purchaseReceipts;
		if (page?.cursor) await this.loadPurchaseReceipts(page.purchase.id, page.cursor);
	}
	async showPurchaseSessions(more = false) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		const cursor = more ? state.purchaseSessions?.cursor : null;
		if (more && !cursor) return;
		if (!await this.run(this.server.purchaseSessions(state.scope, cursor), (page) => {
			this.set({
				purchaseSessions: more ? {
					...page,
					items: [...state.purchaseSessions.items, ...page.items]
				} : page,
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({ purchaseSessions: null });
	}
	async showPurchaseSession(sessionId) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		if (!await this.run(this.server.purchaseSession(state.scope, sessionId), (page) => {
			this.set({
				purchaseSession: page,
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({ purchaseSession: null });
	}
	async showShoppingList(more = false) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		const cursor = more ? state.shoppingList?.cursor : null;
		if (more && !cursor) return;
		if (!await this.run(this.server.shoppingList(state.scope, cursor), (page) => {
			this.set({
				shoppingList: more ? {
					...page,
					items: [...state.shoppingList.items, ...page.items]
				} : page,
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({
			shoppingList: null,
			shoppingSources: null
		});
	}
	async openShoppingItem(scope, key) {
		if (this.owned !== null) return;
		this.set({
			shoppingList: null,
			shoppingSources: null,
			shoppingFocus: void 0
		});
		const items = [];
		const seen = /* @__PURE__ */ new Set();
		let first = null;
		let cursor = null;
		do {
			let found = false;
			if (!await this.run(this.server.shoppingList(scope, cursor), (page) => {
				first ??= page;
				items.push(...page.items);
				found = page.items.some((item) => item.total !== "0" && shoppingItemKey(item) === key);
				cursor = page.cursor;
			}, "unavailable") || this.view?.scope !== scope) return;
			if (found) {
				this.set({
					shoppingList: {
						items,
						cursor
					},
					shoppingFocus: {
						key,
						found
					}
				});
				return;
			}
			if (cursor !== null) {
				if (seen.has(cursor)) {
					this.set({ notice: "unavailable" });
					return;
				}
				seen.add(cursor);
			}
		} while (cursor !== null);
		this.set({
			shoppingList: first,
			shoppingFocus: {
				key,
				found: false
			}
		});
	}
	async showShoppingSources(productId, more = false) {
		const state = this.view;
		if (state === null || state.shoppingList == null || this.owned !== null) return;
		const cursor = more ? state.shoppingSources?.cursor : null;
		if (more && !cursor) return;
		if (!await this.run(this.server.shoppingSources(state.scope, productId, cursor), (page) => {
			this.set({
				shoppingSources: more ? {
					...page,
					items: [...state.shoppingSources.items, ...page.items]
				} : page,
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({ shoppingSources: null });
	}
	async moreShoppingSources() {
		const productId = this.view?.shoppingSources?.item.productId;
		if (productId) await this.showShoppingSources(productId, true);
	}
	async submit(value) {
		const state = this.view;
		if (state === null || state.scope.readOnly || state.pending || state.report === null || this.owned !== null) return;
		let request;
		try {
			const command = inventoryCommand(value);
			if (!mayWrite(state.report, command.action)) return;
			request = {
				key: this.entropy.requestKey(),
				scope: state.scope.key,
				command
			};
			this.journal.save(request);
		} catch {
			this.set({ notice: "unavailable" });
			return;
		}
		this.request = request;
		this.set({
			pending: true,
			notice: null,
			result: null
		});
		await this.send(state.scope, request);
	}
	async recover() {
		const scope = this.view?.scope, request = this.request;
		if (!scope || request === null || this.owned !== null) return;
		if (!await this.run(this.server.original(scope, request), (result) => {
			if (result !== null) this.finish(request, result);
		}, "uncertain") || this.view?.scope !== scope) return;
		if (this.request === null) await this.refresh();
		else if (!scope.readOnly && mayWrite(this.view.report, request.command.action)) await this.send(scope, request);
	}
	set(patch) {
		this.view = {
			...this.view,
			...patch
		};
		this.publish(this.view);
	}
	async load(cursor) {
		const state = this.view;
		if (state === null || this.owned !== null) return;
		if (!await this.run(this.server.read(state.scope, cursor), (page) => {
			this.set({
				report: cursor === null ? page : {
					...page,
					products: [...state.report.products, ...page.products]
				},
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({
			report: null,
			history: null,
			purchases: null,
			purchaseReceipts: null,
			shoppingList: null,
			shoppingSources: null,
			purchaseSessions: null,
			purchaseSession: null,
			barcode: null
		});
	}
	async loadPurchases(cursor) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		if (!await this.run(this.server.purchases(state.scope, cursor), (page) => {
			this.set({
				purchases: cursor === null ? page : {
					...page,
					items: [...state.purchases.items, ...page.items]
				},
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({
			purchases: null,
			purchaseReceipts: null
		});
	}
	async loadPurchaseReceipts(purchaseId, cursor) {
		const state = this.view;
		if (state === null || state.purchases == null && state.purchaseSession == null || this.owned !== null) return;
		if (!await this.run(this.server.purchaseReceipts(state.scope, purchaseId, cursor), (page) => {
			this.set({
				purchaseReceipts: cursor === null ? page : {
					...page,
					items: [...state.purchaseReceipts.items, ...page.items]
				},
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({ purchaseReceipts: null });
	}
	async loadHistory(productId, cursor) {
		const state = this.view;
		if (state === null || state.report === null || this.owned !== null) return;
		if (!await this.run(this.server.history(state.scope, productId, cursor), (page) => {
			const history = cursor === null ? page : {
				...page,
				movements: [...state.history.movements, ...page.movements]
			};
			this.set({
				history,
				notice: state.pending ? state.notice : null
			});
		}, "unavailable") && this.view?.scope === state.scope) this.set({ history: null });
	}
	async send(scope, request) {
		if (await this.run(this.server.send(scope, request), (result) => this.finish(request, result), "uncertain")) await this.refresh();
	}
	finish(request, result) {
		this.journal.clear(request);
		this.request = null;
		this.set({
			pending: false,
			notice: null,
			result
		});
		if ("barcode" in request.command) this.set({ barcode: {
			code: request.command.barcode,
			lookup: null,
			unavailable: false
		} });
	}
	async run(owned, use, notice) {
		this.owned = owned;
		this.set({ busy: true });
		try {
			const value = await owned.result;
			if (this.owned !== owned) return false;
			use(value);
			return true;
		} catch (error) {
			if (this.owned === owned) {
				if (error instanceof EntryReadError && (error.code === "authentication_required" || error.code === "forbidden")) this.set({
					report: null,
					history: null,
					purchases: null,
					purchaseReceipts: null,
					shoppingList: null,
					shoppingSources: null,
					purchaseSessions: null,
					purchaseSession: null,
					shoppingFocus: void 0,
					barcode: null,
					result: null,
					notice: this.view.pending ? "uncertain" : "unavailable"
				});
				else this.set({ notice });
			}
			return false;
		} finally {
			if (this.owned === owned) {
				this.owned = null;
				this.set({ busy: false });
			}
		}
	}
};
export { INVENTORY_JOURNAL_KEY, InventoryController, InventorySessionJournal };
