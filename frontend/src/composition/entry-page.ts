import {HttpInventoryServer} from '../adapters/inventory-http';
import {INVENTORY_JOURNAL_KEY, InventorySessionJournal} from '../adapters/inventory-journal';
import {InventoryController} from '../application/inventory-controller';
import {inventoryCommand} from '../domain/inventory';
import type {InventoryIntent} from '../presentation/domus-inventory';
import {HttpRewardsServer} from '../adapters/reward-http';
import {REWARD_JOURNAL_KEY, RewardsSessionJournal} from '../adapters/reward-journal';
import {RewardsController} from '../application/rewards-controller';
import {rewardCommand} from '../domain/rewards';
import type {RewardsIntent} from '../presentation/domus-rewards';
import {HttpAllocationServer} from '../adapters/allocation-http';
import {ALLOCATION_JOURNAL_KEY, AllocationSessionJournal} from '../adapters/allocation-journal';
import {allocationPolicy} from '../adapters/allocation-values';
import {AllocationController} from '../application/allocation-controller';
import {allocationFingerprint, allocationPerformers, manualPointShares} from '../domain/point-allocation';
import type {AllocationInput, ReviewedAllocation} from '../domain/point-allocation';
import type {AllocationSettingsIntent} from '../presentation/domus-allocation-settings';
import {HttpFamilyServer} from '../adapters/family-http';
import {FamilyController} from '../application/family-controller';
import {civilDate} from '../domain/calendar';
import type {FamilyIntent} from '../presentation/domus-family';
import {HttpRecurrenceServer} from '../adapters/recurrence-http';
import {RECURRENCE_JOURNAL_KEY, RecurrenceSessionJournal} from '../adapters/recurrence-journal';
import {BrowserEntropy, ServerClock} from '../adapters/browser-capabilities';
import {RecurrenceReviewController} from '../application/recurrence-review-controller';
import {reviewDraft} from '../domain/recurrence-review';
import type {ReviewIntent} from '../presentation/domus-recurrence-review';
import {HttpCalendarPreferences} from '../adapters/calendar-preference-http';
import {CALENDAR_JOURNAL_KEY, CalendarSessionJournal} from '../adapters/calendar-journal';
import {CalendarPreferenceController} from '../application/calendar-preferences';
import {HttpCalendarServer} from '../adapters/calendar-http';
import {CalendarController} from '../application/calendar-controller';
import {calendarQuery, calendarToday, WEEK_STARTS} from '../domain/calendar';
import type {CalendarIntent} from '../presentation/domus-calendar';
import {bootstrap} from '../adapters/bootstrap';
import {check, fields, identifier} from '../adapters/http-values';
import type {FetchTransport} from '../adapters/http';
import type {OwnedStorage} from '../adapters/session-journal';
import {EntryRuntime} from './entry-runtime';
import type {EntryBrowser} from './entry-runtime';
import {language, message} from '../presentation/messages';
import type {DomusApp, EntryIntent} from '../presentation/domus-app';
import {revisionValue} from '../domain/administration';
import type {TaskIntent} from '../presentation/domus-tasks';
import {taskQuantity, taskScheduleDraft, TASK_PRIORITIES} from '../domain/tasks';
import type {TaskPriority} from '../domain/tasks';
import type {AdministrationIntent} from '../presentation/domus-administration';
import {administrationCommand} from '../domain/administration-commands';
import '../presentation/domus-app';

export interface EntryPage extends EventTarget {
  readonly document: Document;
  readonly location: Pick<Location, 'href' | 'assign' | 'reload'>;
  readonly navigator: Pick<Navigator, 'language'>;
  readonly performance: Pick<Performance, 'now'>;
  readonly crypto: Pick<Crypto, 'getRandomValues'>;
  readonly sessionStorage: OwnedStorage;
  readonly fetch: FetchTransport;
  setTimeout(tick: () => void, delay: number): number;
  clearTimeout(id: number): void;
  litNonce?: string;
}
export interface PageMount {readonly ready: Promise<void>; dispose(): void;}
const mounts = new WeakMap<Document, () => void>();

/** DOM values are untrusted; unknown fields never become a URL, actor or arbitrary method call. */
export function decodeIntent(value: unknown): EntryIntent | null {
  try {
    const item = fields(value, ['type'], ['name', 'timeZone', 'key', 'language']);
    const type = item.type;
    if (type === 'setup') {
      fields(value, ['type', 'name', 'timeZone'], []); const {name, timeZone} = item;
      check(typeof name === 'string' && typeof timeZone === 'string'); return {type, name, timeZone};
    }
    if (type === 'recover' || type === 'dismiss') {
      fields(value, ['type', 'key'], []); return {type, key: identifier(item.key)};
    }
    if (type === 'language') {
      fields(value, ['type', 'language'], []); const locale = item.language;
      check(locale === 'en' || locale === 'es'); return {type, language: locale};
    }
    check(type === 'refresh' || type === 'request_membership' || type === 'logout' || type === 'sign_in' || type === 'reopen');
    fields(value, ['type'], []); return {type};
  } catch {return null;}
}

/** Closed administration events never supply a principal, a context, a URL or an arbitrary transport method. */
export function decodeAdministrationIntent(value:unknown):AdministrationIntent|null {
  try {
    const item=fields(value,['type'],['command','key']),type=item.type;
    if(type==='submit') {fields(value,['type','command'],[]);return {type,command:administrationCommand(item.command)};}
    if(type==='recover'||type==='dismiss') {fields(value,['type','key'],[]);return {type,key:identifier(item.key)};}
    check(type==='refresh');fields(value,['type'],[]);return {type};
  }catch{return null;}
}

/** Task events contain business inputs only, never a principal, URL, context or raw transport request. */
function allocationInput(value: unknown): AllocationInput {
  const item = fields(value, ['performerIds'], ['manualShares']);
  const performerIds = allocationPerformers(item.performerIds, identifier);
  return {performerIds, ...Object.hasOwn(item, 'manualShares') ? {manualShares: manualPointShares(item.manualShares, performerIds)} : {}};
}

function reviewedAllocation(value: unknown): ReviewedAllocation {
  const item = fields(value, ['performerIds','occurrenceId','revision','fingerprint'], ['manualShares']);
  return {...allocationInput({performerIds: item.performerIds,
    ...Object.hasOwn(item, 'manualShares') ? {manualShares: item.manualShares} : {}}),
    occurrenceId: identifier(item.occurrenceId), revision: revisionValue(item.revision),
    fingerprint: allocationFingerprint(item.fingerprint)};
}

export function decodeTaskIntent(value: unknown): TaskIntent | null {
  try {
    const item = fields(value, ['type'], ['title', 'description', 'priority', 'schedule', 'occurrenceId', 'materialUsages', 'decision', 'reason', 'key', 'categoryId', 'label', 'revision', 'reviewed']);
    const type = item.type;
    if (type === 'create') {
      fields(value, ['type', 'title', 'description', 'priority'], ['schedule', 'categoryId']);
      check(typeof item.title === 'string' && typeof item.description === 'string' && typeof item.priority === 'string'
        && TASK_PRIORITIES.includes(item.priority as TaskPriority));
      return {type, title: item.title, description: item.description, priority: item.priority as TaskPriority,
        ...Object.hasOwn(item, 'schedule') ? {schedule: taskScheduleDraft(item.schedule)} : {},
        ...Object.hasOwn(item, 'categoryId') ? {categoryId: identifier(item.categoryId)} : {}};
    }
    if (type === 'createCategory') {
      fields(value, ['type', 'label'], []); check(typeof item.label === 'string');
      return {type, label: item.label};
    }
    if (type === 'renameCategory' || type === 'archiveCategory') {
      fields(value, ['type', 'categoryId', 'revision', ...type === 'renameCategory' ? ['label'] : []], []);
      const categoryId = identifier(item.categoryId), revision = revisionValue(item.revision);
      if (type === 'archiveCategory') return {type, categoryId, revision};
      check(typeof item.label === 'string');
      return {type, categoryId, revision, label: item.label};
    }
    if (type === 'complete') {
      fields(value, ['type', 'materialUsages'], ['reviewed']);
      check(item.materialUsages === null || Array.isArray(item.materialUsages) && item.materialUsages.length <= 32);
      const materialUsages = item.materialUsages === null ? null : Object.freeze((item.materialUsages as unknown[]).map(raw => {
        const usage = fields(raw, ['line_id', 'quantity'], []);
        return Object.freeze({line_id: identifier(usage.line_id), quantity: taskQuantity(usage.quantity)});
      }));
      return {type, materialUsages, ...Object.hasOwn(item, 'reviewed') ? {reviewed: reviewedAllocation(item.reviewed)} : {}};
    }
    if (type === 'verify' || type === 'reopen') {
      fields(value, type === 'verify' ? ['type', 'decision', 'reason'] : ['type', 'reason'], []);
      check(typeof item.reason === 'string');
      if (type === 'reopen') return {type, reason: item.reason};
      check(item.decision === 'approved' || item.decision === 'rejected'); return {type, decision: item.decision, reason: item.reason};
    }
    if (type === 'select') {fields(value, ['type', 'occurrenceId'], []); return {type, occurrenceId: identifier(item.occurrenceId)};}
    if (type === 'recover' || type === 'dismiss') {fields(value, ['type', 'key'], []); return {type, key: identifier(item.key)};}
    fields(value, ['type'], []); check(type === 'refresh' || type === 'more' || type === 'claim'); return {type};
  } catch {return null;}
}

export function decodeCalendarIntent(value: unknown): CalendarIntent | null {
  try {
    const item = fields(value, ['type'], ['query','weekStart']);
    if (item.type === 'load') {
      fields(value, ['type', 'query'], []); check(calendarQuery(item.query));
      return {type: 'load', query: item.query};
    }
    if (item.type === 'setWeekStart') {
      const {weekStart} = fields(value, ['type','weekStart'], []);
      check(weekStart === WEEK_STARTS[0] || weekStart === WEEK_STARTS[1]);
      return {type:'setWeekStart',weekStart};
    }
    fields(value, ['type'], []);
    check(item.type === 'more' || item.type === 'recoverPreference' || item.type === 'refreshPreference');
    return {type:item.type};
  } catch {return null;}
}

export function decodeReviewIntent(value: unknown): ReviewIntent | null {
  try {
    const {type} = fields(value, ['type'], ['draft','key']);
    if (type === 'preview') return {type, draft: reviewDraft(fields(value, ['type','draft'], []).draft)};
    if (type === 'recover' || type === 'forget') return {type, key: identifier(fields(value, ['type','key'], []).key)};
    fields(value, ['type'], []); check(type === 'open' || type === 'close' || type === 'apply');
    return {type};
  } catch {return null;}
}

export function decodeInventoryIntent(value: unknown): InventoryIntent | null {
  try {
    const {type} = fields(value, ['type'], ['command', 'productId', 'purchaseId', 'sessionId']);
    if (type === 'submit') return {type, command: inventoryCommand(fields(value, ['type','command'], []).command)};
    if (type === 'history' || type === 'shopping-sources') return {type, productId: identifier(fields(value, ['type','productId'], []).productId)};
    if (type === 'purchase-receipts') return {type, purchaseId: identifier(fields(value, ['type','purchaseId'], []).purchaseId)};
    if (type === 'purchase-session') return {type, sessionId: identifier(fields(value, ['type','sessionId'], []).sessionId)};
    fields(value, ['type'], []);
    check(type === 'refresh' || type === 'more' || type === 'recover' || type === 'more-history' || type === 'close-history'
      || type === 'purchases' || type === 'more-purchases' || type === 'more-purchase-receipts'
      || type === 'shopping-list' || type === 'more-shopping-list' || type === 'more-shopping-sources'
      || type === 'purchase-sessions' || type === 'more-purchase-sessions');
    return {type};
  } catch {return null;}
}

/** Wire only this document's owned nodes/capabilities; never inspect the HA parent or private storage. */
export function mountEntry(page: EntryPage): PageMount {
  const doc = page.document; mounts.get(doc)?.();
  const lifetime = new AbortController(), widget = new AbortController();
  let calendarPreference: CalendarPreferenceController | null = null;
  let family: FamilyController | null = null;
  let rewards: RewardsController | null = null;
  let inventory: InventoryController | null = null;
  let allocation: AllocationController | null = null;
  let calendar: CalendarController | null = null, review: RecurrenceReviewController | null = null;
  let stopped = false, runtime: EntryRuntime | null = null, app: DomusApp | null = null, error: HTMLElement | null = null;
  let localeOwner:string|null=null,preferenceIdentity:string|null=null,hadPreference=false,temporaryLanguage=false,temporaryContext:string|null=null;
  const dispose = () => {
    if (stopped) return;
    stopped = true; widget.abort(); lifetime.abort(); runtime?.dispose(); calendar?.bind(null); family?.bind(null); rewards?.bind(null); inventory?.bind(null); allocation?.bind(null); calendarPreference?.bind(null); review?.bind(null); error?.remove();
    if (mounts.get(doc) === dispose) mounts.delete(doc);
  };
  mounts.set(doc, dispose);
  page.addEventListener('pagehide', event => {
    if (!('persisted' in event) || event.persisted !== true) dispose();
  }, {signal: lifetime.signal});
  const fail = () => {
    if (stopped || error !== null) return;
    widget.abort(); runtime?.dispose(); calendar?.bind(null); family?.bind(null); rewards?.bind(null); inventory?.bind(null); allocation?.bind(null); calendarPreference?.bind(null); review?.bind(null); app?.remove();
    const locale = language(null, page.navigator.language); doc.documentElement.lang = locale;
    error = doc.createElement('main'); error.id = 'domus-entry-error';
    const heading = doc.createElement('h1'), body = doc.createElement('p'), action = doc.createElement('p'), reload = doc.createElement('button');
    heading.textContent = message('state_unavailable', locale); body.textContent = message('body_unavailable', locale);
    action.textContent = message('pageErrorAction', locale); reload.textContent = message('reload', locale); reload.type = 'button';
    reload.addEventListener('click', () => {try {page.location.reload();} catch {reload.disabled = true;}}, {signal: lifetime.signal});
    error.append(heading, body, action, reload); doc.body.append(error);
  };
  let ready: Promise<void>;
  try {
    const data = doc.querySelectorAll('#domus-bootstrap'), roots = doc.querySelectorAll('#domus-entry');
    check(data.length === 1 && data[0].tagName === 'SCRIPT' && data[0].getAttribute('type') === 'application/json');
    check(roots.length === 1 && roots[0].tagName === 'DIV');
    const source = bootstrap(data[0].textContent, page.location.href);
    // Lit's style-element fallback reads this public document CSP nonce; it carries no authority.
    page.litNonce = source.styleNonce;
    const element = doc.createElement('domus-app'); app = element;
    element.language = language(null, page.navigator.language); element.deployment = source.target.deployment;
    doc.documentElement.lang = element.language;
    const browser: EntryBrowser = {transport: (path, init) => page.fetch(path, init), storage: () => page.sessionStorage,
      elapsed: () => page.performance.now(), random: bytes => page.crypto.getRandomValues(bytes),
      navigate: path => page.location.assign(path), events: page, visibility: doc,
      schedule: (tick, delay) => {const id = page.setTimeout(tick, delay); return () => page.clearTimeout(id);}};
    const calendarController = new CalendarController(new HttpCalendarServer(source.target, browser.transport),
      view => {element.calendar = view;});
    calendar = calendarController;
    const preferences = new CalendarPreferenceController(new HttpCalendarPreferences(source.target,browser.transport),
      new CalendarSessionJournal({getItem:key => browser.storage().getItem(key),
        setItem:(key,value) => browser.storage().setItem(key,value), removeItem:key => browser.storage().removeItem(key)}),
      new ServerClock(browser.elapsed), new BrowserEntropy(browser.random), view => {element.calendarPreference = view;});
    calendarPreference = preferences;
    const syncCalendar = () => {
      const entry = element.view, tasks = element.tasks;
      if (element.workspaceDestination === 'calendar' && entry?.phase === 'ready' && entry.decision?.state === 'active'
          && entry.household && tasks?.phase === 'ready' && tasks.session && tasks.access && tasks.scopeKey) {
        element.calendarToday = calendarToday(tasks.session.serverTime, entry.household.timeZone);
        calendarController.bind({key: tasks.scopeKey, context: tasks.session.context, memberId: tasks.access.memberId});
        preferences.bind({key:tasks.scopeKey,context:tasks.session.context,memberId:tasks.access.memberId,
          serverTime:tasks.session.serverTime,expiresAt:tasks.session.expiresAt,readOnly:tasks.readOnly});
        element.calendarScopeKey = tasks.scopeKey;
      } else {
        calendarController.bind(null); preferences.bind(null); element.calendarScopeKey = null;
      }
    };
    const familyController = new FamilyController(new HttpFamilyServer(source.target, browser.transport),
      view => {element.family = view;});
    family = familyController;
    const rewardsController = new RewardsController(new HttpRewardsServer(source.target, browser.transport),
      new RewardsSessionJournal({getItem: key => browser.storage().getItem(key),
        setItem: (key, value) => browser.storage().setItem(key, value), removeItem: key => browser.storage().removeItem(key)}),
      new BrowserEntropy(browser.random), view => {element.rewards = view;}, () => familyController.refresh());
    rewards = rewardsController;
    element.addEventListener('domus-rewards-intent', async event => {
      if (event.target !== element) return;
      let intent: RewardsIntent;
      try {
        const raw = (event as CustomEvent<unknown>).detail;
        const item = fields(raw, ['type'], ['command']);
        if (item.type === 'submit') {
          fields(raw, ['type','command'], []);
          intent = {type: 'submit', command: rewardCommand(item.command)};
        } else {
          fields(raw, ['type'], []);
          check(item.type === 'refresh' || item.type === 'more' || item.type === 'recover');
          intent = {type: item.type};
        }
      } catch {return;}
      if (intent.type === 'refresh') await rewardsController.refresh();
      if (intent.type === 'more') await rewardsController.more();
      if (intent.type === 'recover') await rewardsController.recover();
      if (intent.type === 'submit') await rewardsController.submit(intent.command);
    }, {signal: widget.signal});
    const syncFamily = () => {
      const entry = element.view, tasks = element.tasks;
      if (element.workspaceDestination === 'family' && entry?.phase === 'ready' && entry.decision?.state === 'active'
          && entry.household && tasks?.phase === 'ready' && tasks.session && tasks.scopeKey && tasks.access) {
        const today = calendarToday(tasks.session.serverTime, entry.household.timeZone);
        const key = JSON.stringify([tasks.scopeKey, entry.household.revision]);
        element.familyToday = today; element.familyScopeKey = key;
        familyController.bind({key, today, context: tasks.session.context});
        rewardsController.bind({key, context: tasks.session.context, memberId: tasks.access.memberId, readOnly: tasks.readOnly});
      } else {
        familyController.bind(null); rewardsController.bind(null); element.familyScopeKey = null;
      }
    };
    element.addEventListener('domus-family-intent', async event => {
      const intent = (event as CustomEvent<FamilyIntent>).detail;
      if (intent?.type === 'refresh') await familyController.refresh();
      if (intent?.type === 'more') await familyController.more();
      if (intent?.type === 'period' && (intent.mode === 'week' || intent.mode === 'month') && civilDate(intent.anchor))
        await familyController.select(intent.mode, intent.anchor);
    }, {signal: widget.signal});
    const reviews = new RecurrenceReviewController(new HttpRecurrenceServer(source.target, browser.transport),
      new RecurrenceSessionJournal({getItem: key => browser.storage().getItem(key),
        setItem: (key, value) => browser.storage().setItem(key, value)}), new ServerClock(browser.elapsed), new BrowserEntropy(browser.random),
      view => {element.recurrenceReview = view;});
    review = reviews;
    const syncReview = () => {
      const entry = element.view, tasks = element.tasks;
      if (element.workspaceDestination === 'tasks' && entry?.phase === 'ready'
          && entry.decision?.state === 'active'
          && tasks?.phase === 'ready' && tasks.session && tasks.scopeKey && tasks.access?.canReviewSchedule) {
        const {context, serverTime, expiresAt} = tasks.session;
        reviews.bind({key: tasks.scopeKey, context, serverTime, expiresAt, readOnly: tasks.readOnly,
          occurrenceId: tasks.detail?.occurrenceId ?? null});
      } else reviews.bind(null);
    };
    const allocations = new AllocationController(new HttpAllocationServer(source.target, browser.transport),
      new AllocationSessionJournal({getItem: key => browser.storage().getItem(key),
        setItem: (key, value) => browser.storage().setItem(key, value), removeItem: key => browser.storage().removeItem(key)}),
      new BrowserEntropy(browser.random), view => {element.allocation = view;});
    allocation = allocations;
    const syncAllocation = () => {
      const entry = element.view, tasks = element.tasks, destination = element.workspaceDestination;
      if (entry?.phase !== 'ready' || entry.decision?.state !== 'active' || tasks?.phase !== 'ready'
          || !tasks.session || !tasks.scopeKey || !tasks.access) {allocations.bind(null); return;}
      const canManage = tasks.access.canManagePoints === true;
      const detail = tasks.detail;
      if (destination === 'family' && canManage) {
        allocations.bind({key: tasks.scopeKey, context: tasks.session.context, definitionId: null,
          work: null, readOnly: tasks.readOnly, canManage});
      } else if (destination === 'tasks' && detail !== null) {
        allocations.bind({key: tasks.scopeKey, context: tasks.session.context, definitionId: detail.definitionId,
          work: {occurrenceId: detail.occurrenceId, revision: detail.revision,
            canComplete: detail.allowedActions.includes('complete'), requiresManual: detail.completionPoints === 'manual'},
          readOnly: tasks.readOnly, canManage});
      } else allocations.bind(null);
    };
    element.addEventListener('domus-allocation-settings', async event => {
      if (event.target !== element) return;
      const value = (event as CustomEvent<unknown>).detail;
      let intent: AllocationSettingsIntent;
      try {
        const item = fields(value, ['type'], ['policy']);
        if (item.type === 'save') {
          fields(value, ['type','policy'], []);
          intent = {type: 'save', policy: item.policy === null ? null : allocationPolicy(item.policy)};
        } else {
          fields(value, ['type'], []); check(item.type === 'refresh' || item.type === 'recover'); intent = {type: item.type};
        }
      } catch {return;}
      if (intent.type === 'save') await allocations.save(intent.policy);
      if (intent.type === 'recover') await allocations.recover();
      if (intent.type === 'refresh') await allocations.refresh();
    }, {signal: widget.signal});
    element.addEventListener('domus-allocation-preview', async event => {
      if (event.target !== element) return;
      let input: AllocationInput;
      try {input = allocationInput((event as CustomEvent<unknown>).detail);} catch {return;}
      await allocations.preview(input);
    }, {signal: widget.signal});
    const inventoryController = new InventoryController(new HttpInventoryServer(source.target, browser.transport),
      new InventorySessionJournal({getItem:key => browser.storage().getItem(key),
        setItem:(key,value) => browser.storage().setItem(key,value), removeItem:key => browser.storage().removeItem(key)}),
      new BrowserEntropy(browser.random), view => {element.inventory = view;});
    inventory = inventoryController;
    const syncInventory = () => {
      const entry = element.view;
      if (element.workspaceDestination === 'inventory' && entry?.phase === 'ready'
          && entry.decision?.householdReadable && entry.session) {
        const context = entry.session.context;
        const key = JSON.stringify([context.installationId, context.channel, context.subject]);
        inventoryController.bind({key, context, readOnly:entry.decision.readOnly});
      } else inventoryController.bind(null);
    };
    element.addEventListener('domus-inventory-intent', async event => {
      if (event.target !== element) return;
      const intent = decodeInventoryIntent((event as CustomEvent<unknown>).detail);
      if (intent?.type === 'refresh') await inventoryController.refresh();
      if (intent?.type === 'more') await inventoryController.more();
      if (intent?.type === 'recover') await inventoryController.recover();
      if (intent?.type === 'history') await inventoryController.showHistory(intent.productId);
      if (intent?.type === 'more-history') await inventoryController.moreHistory();
      if (intent?.type === 'close-history') inventoryController.closeHistory();
      if (intent?.type === 'purchases') await inventoryController.showPurchases();
      if (intent?.type === 'more-purchases') await inventoryController.morePurchases();
      if (intent?.type === 'purchase-receipts') await inventoryController.showPurchaseReceipts(intent.purchaseId);
      if (intent?.type === 'more-purchase-receipts') await inventoryController.morePurchaseReceipts();
      if (intent?.type === 'purchase-sessions') await inventoryController.showPurchaseSessions();
      if (intent?.type === 'more-purchase-sessions') await inventoryController.showPurchaseSessions(true);
      if (intent?.type === 'purchase-session') await inventoryController.showPurchaseSession(intent.sessionId);
      if (intent?.type === 'shopping-list') await inventoryController.showShoppingList();
      if (intent?.type === 'more-shopping-list') await inventoryController.showShoppingList(true);
      if (intent?.type === 'shopping-sources') await inventoryController.showShoppingSources(intent.productId);
      if (intent?.type === 'more-shopping-sources') await inventoryController.moreShoppingSources();
      if (intent?.type === 'submit') await inventoryController.submit(intent.command);
    }, {signal:widget.signal});
    const syncWorkspace = () => {
      const fragment = new URL(page.location.href).hash;
      element.workspaceDestination = fragment === '#overview' ? 'overview' : fragment === '#household' ? 'household'
        : fragment === '#tasks' ? 'tasks' : fragment === '#calendar' ? 'calendar' : fragment === '#family' ? 'family' : fragment === '#inventory' ? 'inventory' : null;
      syncCalendar(); syncReview(); syncFamily(); syncAllocation(); syncInventory();
    };
    syncWorkspace();
    page.addEventListener('hashchange', syncWorkspace, {signal: widget.signal});
    const active = new EntryRuntime(source.target, browser, (view,administration,tasks) => {
      element.view=view;element.administration=administration;element.tasks=tasks;syncCalendar();syncReview();syncFamily();syncAllocation();syncInventory();
      const context=administration?.session?.context,member=administration?.access?.member;
      const contextKey=context?JSON.stringify([context.installationId,context.channel,context.subject]):null;
      const owner=contextKey!==null&&administration?.access?.state==='active'&&member?JSON.stringify([contextKey,member.memberId]):null;
      const retired=view.phase==='closed'||view.notice==='context_changed'||(view.phase==='ready'&&view.decision?.state!=='active');
      if(retired||(administration!==null&&owner===null)) {
        const entryContext=view.session?.context;
        const entryKey=entryContext?JSON.stringify([entryContext.installationId,entryContext.channel,entryContext.subject]):null;
        const keepUnboundChoice=localeOwner===null&&temporaryLanguage&&temporaryContext===entryKey;
        localeOwner=null;preferenceIdentity=null;hadPreference=false;
        if(!keepUnboundChoice){temporaryLanguage=false;temporaryContext=null;element.language=language(null,page.navigator.language);}
      }else if(owner!==null) {
        if(owner!==localeOwner) {
          const keepInitialChoice=localeOwner===null&&temporaryLanguage&&temporaryContext===contextKey;
          localeOwner=owner;preferenceIdentity=null;hadPreference=false;
          if(!keepInitialChoice){temporaryLanguage=false;temporaryContext=null;element.language=language(null,page.navigator.language);}
        }
        const preferences=administration!.preferences;
        if(preferences!==null) {
          const identity=JSON.stringify([preferences.revision,preferences.locale,preferences.routine_participation_summaries]);
          if((identity!==preferenceIdentity&&(preferenceIdentity!==null||preferences.locale!==null||!temporaryLanguage))
              ||(!hadPreference&&!temporaryLanguage)) {
            element.language=language(preferences.locale,page.navigator.language);temporaryLanguage=false;temporaryContext=null;
          }
          preferenceIdentity=identity;hadPreference=true;
        }else {hadPreference=false;if(!temporaryLanguage)element.language=language(null,page.navigator.language);}
      }
      doc.documentElement.lang=element.language;
    }, fail); runtime = active;
    element.addEventListener('domus-detached', dispose, {signal: widget.signal});
    element.addEventListener('domus-intent', async event => {
      if (event.target !== element) return;
      try {
        const intent = decodeIntent((event as CustomEvent<unknown>).detail);
        if (intent === null) return;
        switch (intent.type) {
          case 'language': {
            element.language=intent.language;doc.documentElement.lang=intent.language;temporaryLanguage=true;
            const context=active.view.session?.context;
            temporaryContext=context?JSON.stringify([context.installationId,context.channel,context.subject]):null;break;
          }
          case 'setup': await active.submitSetup(intent.name, intent.timeZone); break;
          case 'request_membership': await active.requestMembership(); break;
          case 'recover': await active.recover(intent.key); break;
          case 'dismiss': await active.dismiss(intent.key); break;
          case 'refresh': await active.refresh(); break;
          case 'logout': {
            const signOut = active.logout();
            const storage = browser.storage();
            storage.removeItem(ALLOCATION_JOURNAL_KEY);
            storage.removeItem(REWARD_JOURNAL_KEY);
            storage.removeItem(INVENTORY_JOURNAL_KEY);
            storage.removeItem(CALENDAR_JOURNAL_KEY);
            storage.removeItem(RECURRENCE_JOURNAL_KEY);
            await signOut;
            break;
          }
          case 'sign_in': active.signIn(); break;
          case 'reopen': active.reopen(); break;
        }
      } catch {fail();}
    }, {signal: widget.signal});
    element.addEventListener('domus-administration-intent',async event=>{
      if(event.target!==element)return;
      try {
        const intent=decodeAdministrationIntent((event as CustomEvent<unknown>).detail);if(intent===null)return;
        switch(intent.type){
          case 'submit':await active.submitAdministration(intent.command);break;
          case 'recover':await active.recoverAdministration(intent.key);break;
          case 'dismiss':await active.dismissAdministration(intent.key);break;
          case 'refresh':await active.refresh();break;
        }
      }catch{fail();}
    },{signal:widget.signal});
    element.addEventListener('domus-task-intent', async event => {
      if (event.target !== element) return;
      try {
        const intent = decodeTaskIntent((event as CustomEvent<unknown>).detail); if (intent === null) return;
        switch (intent.type) {
          case 'refresh': await active.refresh(); break;
          case 'more': await active.taskWork(controller => controller.more()); break;
          case 'select': await active.taskWork(controller => controller.select(intent.occurrenceId)); break;
          case 'create': await active.taskWork(controller => controller.create(intent.title, intent.description, intent.priority, intent.schedule, intent.categoryId)); break;
          case 'createCategory': await active.taskWork(controller => controller.createCategory(intent.label)); break;
          case 'renameCategory': await active.taskWork(controller => controller.renameCategory(intent.categoryId, intent.revision, intent.label)); break;
          case 'archiveCategory': await active.taskWork(controller => controller.archiveCategory(intent.categoryId, intent.revision)); break;
          case 'claim': await active.taskWork(controller => controller.claim()); break;
          case 'complete':
            await active.taskWork(controller => controller.complete(intent.materialUsages, ...intent.reviewed === undefined ? [] : [intent.reviewed]));
            break;
          case 'verify': await active.taskWork(controller => controller.verify(intent.decision, intent.reason)); break;
          case 'reopen': await active.taskWork(controller => controller.reopen(intent.reason)); break;
          case 'recover': await active.taskWork(controller => controller.recover(intent.key)); break;
          case 'dismiss': await active.taskWork(controller => controller.dismiss(intent.key)); break;
        }
      } catch {fail();}
    }, {signal: widget.signal});
    element.addEventListener('domus-calendar-intent', async event => {
      if (event.target !== element) return;
      const intent = decodeCalendarIntent((event as CustomEvent<unknown>).detail);
      if (intent?.type === 'load') await calendarController.load(intent.query);
      if (intent?.type === 'more') await calendarController.more();
      if (intent?.type === 'setWeekStart') await preferences.save(intent.weekStart);
      if (intent?.type === 'recoverPreference') await preferences.recover();
      if (intent?.type === 'refreshPreference') await preferences.refresh();
    }, {signal: widget.signal});
    element.addEventListener('domus-review-intent', async event => {
      if (event.target !== element) return;
      const intent = decodeReviewIntent((event as CustomEvent<unknown>).detail);
      if (intent === null) return;
      switch (intent.type) {
        case 'open': await reviews.open(); break;
        case 'close': reviews.close(); break;
        case 'preview': await reviews.preview(intent.draft); break;
        case 'apply': await reviews.apply(); break;
        case 'recover': await reviews.recover(intent.key); break;
        case 'forget': reviews.forget(intent.key); break;
      }
    }, {signal: widget.signal});
    roots[0].replaceChildren(element);
    ready = active.start().catch(() => {fail();});
  } catch {fail(); ready = Promise.resolve();}
  return Object.freeze({ready, dispose});
}
