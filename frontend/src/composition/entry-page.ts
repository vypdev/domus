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
export function decodeTaskIntent(value: unknown): TaskIntent | null {
  try {
    const item = fields(value, ['type'], ['title', 'description', 'priority', 'schedule', 'occurrenceId', 'materialUsages', 'decision', 'reason', 'key']);
    const type = item.type;
    if (type === 'create') {
      fields(value, ['type', 'title', 'description', 'priority'], ['schedule']);
      check(typeof item.title === 'string' && typeof item.description === 'string' && typeof item.priority === 'string'
        && TASK_PRIORITIES.includes(item.priority as TaskPriority));
      return {type, title: item.title, description: item.description, priority: item.priority as TaskPriority,
        ...Object.hasOwn(item, 'schedule') ? {schedule: taskScheduleDraft(item.schedule)} : {}};
    }
    if (type === 'complete') {
      fields(value, ['type', 'materialUsages'], []);
      check(item.materialUsages === null || Array.isArray(item.materialUsages) && item.materialUsages.length <= 32);
      const materialUsages = item.materialUsages === null ? null : Object.freeze((item.materialUsages as unknown[]).map(raw => {
        const usage = fields(raw, ['line_id', 'quantity'], []);
        return Object.freeze({line_id: identifier(usage.line_id), quantity: taskQuantity(usage.quantity)});
      }));
      return {type, materialUsages};
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

/** Wire only this document's owned nodes/capabilities; never inspect the HA parent or private storage. */
export function mountEntry(page: EntryPage): PageMount {
  const doc = page.document; mounts.get(doc)?.();
  const lifetime = new AbortController(), widget = new AbortController();
  let calendarPreference: CalendarPreferenceController | null = null;
  let calendar: CalendarController | null = null, review: RecurrenceReviewController | null = null;
  let stopped = false, runtime: EntryRuntime | null = null, app: DomusApp | null = null, error: HTMLElement | null = null;
  let localeOwner:string|null=null,preferenceIdentity:string|null=null,hadPreference=false,temporaryLanguage=false,temporaryContext:string|null=null;
  const dispose = () => {
    if (stopped) return;
    stopped = true; widget.abort(); lifetime.abort(); runtime?.dispose(); calendar?.bind(null); calendarPreference?.bind(null); review?.bind(null); error?.remove();
    if (mounts.get(doc) === dispose) mounts.delete(doc);
  };
  mounts.set(doc, dispose);
  page.addEventListener('pagehide', event => {
    if (!('persisted' in event) || event.persisted !== true) dispose();
  }, {signal: lifetime.signal});
  const fail = () => {
    if (stopped || error !== null) return;
    widget.abort(); runtime?.dispose(); calendar?.bind(null); calendarPreference?.bind(null); review?.bind(null); app?.remove();
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
    const syncWorkspace = () => {
      const fragment = new URL(page.location.href).hash;
      element.workspaceDestination = fragment === '#overview' ? 'overview' : fragment === '#household' ? 'household'
        : fragment === '#tasks' ? 'tasks' : fragment === '#calendar' ? 'calendar' : null;
      syncCalendar(); syncReview();
    };
    syncWorkspace();
    page.addEventListener('hashchange', syncWorkspace, {signal: widget.signal});
    const active = new EntryRuntime(source.target, browser, (view,administration,tasks) => {
      element.view=view;element.administration=administration;element.tasks=tasks;syncCalendar();syncReview();
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
          case 'create': await active.taskWork(controller => controller.create(intent.title, intent.description, intent.priority, intent.schedule)); break;
          case 'claim': await active.taskWork(controller => controller.claim()); break;
          case 'complete': await active.taskWork(controller => controller.complete(intent.materialUsages)); break;
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
