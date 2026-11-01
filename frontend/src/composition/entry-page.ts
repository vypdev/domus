import {bootstrap} from '../adapters/bootstrap';
import {check, fields, identifier} from '../adapters/http-values';
import type {FetchTransport} from '../adapters/http';
import type {OwnedStorage} from '../adapters/session-journal';
import {EntryRuntime} from './entry-runtime';
import type {EntryBrowser} from './entry-runtime';
import {language, message} from '../presentation/messages';
import type {DomusApp, EntryIntent} from '../presentation/domus-app';
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

/** Wire only this document's owned nodes/capabilities; never inspect the HA parent or private storage. */
export function mountEntry(page: EntryPage): PageMount {
  const doc = page.document; mounts.get(doc)?.();
  const lifetime = new AbortController(), widget = new AbortController();
  let stopped = false, runtime: EntryRuntime | null = null, app: DomusApp | null = null, error: HTMLElement | null = null;
  const dispose = () => {
    if (stopped) return;
    stopped = true; widget.abort(); lifetime.abort(); runtime?.dispose(); error?.remove();
    if (mounts.get(doc) === dispose) mounts.delete(doc);
  };
  mounts.set(doc, dispose);
  page.addEventListener('pagehide', event => {
    if (!('persisted' in event) || event.persisted !== true) dispose();
  }, {signal: lifetime.signal});
  const fail = () => {
    if (stopped || error !== null) return;
    widget.abort(); runtime?.dispose(); app?.remove();
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
    const active = new EntryRuntime(source.target, browser, view => {element.view = view;}, fail); runtime = active;
    element.addEventListener('domus-detached', dispose, {signal: widget.signal});
    element.addEventListener('domus-intent', async event => {
      if (event.target !== element) return;
      try {
        const intent = decodeIntent((event as CustomEvent<unknown>).detail);
        if (intent === null) return;
        switch (intent.type) {
          case 'language': element.language = intent.language; doc.documentElement.lang = intent.language; break;
          case 'setup': await active.submitSetup(intent.name, intent.timeZone); break;
          case 'request_membership': await active.requestMembership(); break;
          case 'recover': await active.recover(intent.key); break;
          case 'dismiss': await active.dismiss(intent.key); break;
          case 'refresh': await active.refresh(); break;
          case 'logout': await active.logout(); break;
          case 'sign_in': active.signIn(); break;
          case 'reopen': active.reopen(); break;
        }
      } catch {fail();}
    }, {signal: widget.signal});
    roots[0].replaceChildren(element);
    ready = active.start().catch(() => {fail();});
  } catch {fail(); ready = Promise.resolve();}
  return Object.freeze({ready, dispose});
}
