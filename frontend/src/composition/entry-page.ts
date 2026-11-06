import {bootstrap} from '../adapters/bootstrap';
import {check, fields, identifier} from '../adapters/http-values';
import type {FetchTransport} from '../adapters/http';
import type {OwnedStorage} from '../adapters/session-journal';
import {EntryRuntime} from './entry-runtime';
import type {EntryBrowser} from './entry-runtime';
import {language, message} from '../presentation/messages';
import type {DomusApp, EntryIntent} from '../presentation/domus-app';
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

/** Wire only this document's owned nodes/capabilities; never inspect the HA parent or private storage. */
export function mountEntry(page: EntryPage): PageMount {
  const doc = page.document; mounts.get(doc)?.();
  const lifetime = new AbortController(), widget = new AbortController();
  let stopped = false, runtime: EntryRuntime | null = null, app: DomusApp | null = null, error: HTMLElement | null = null;
  let localeOwner:string|null=null,preferenceIdentity:string|null=null,hadPreference=false,temporaryLanguage=false,temporaryContext:string|null=null;
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
    const syncWorkspace = () => {
      const fragment = new URL(page.location.href).hash;
      element.workspaceDestination = fragment === '#overview' ? 'overview' : fragment === '#household' ? 'household' : null;
    };
    syncWorkspace();
    page.addEventListener('hashchange', syncWorkspace, {signal: widget.signal});
    const browser: EntryBrowser = {transport: (path, init) => page.fetch(path, init), storage: () => page.sessionStorage,
      elapsed: () => page.performance.now(), random: bytes => page.crypto.getRandomValues(bytes),
      navigate: path => page.location.assign(path), events: page, visibility: doc,
      schedule: (tick, delay) => {const id = page.setTimeout(tick, delay); return () => page.clearTimeout(id);}};
    const active = new EntryRuntime(source.target, browser, (view,administration) => {
      element.view=view;element.administration=administration;
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
          case 'logout': await active.logout(); break;
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
    roots[0].replaceChildren(element);
    ready = active.start().catch(() => {fail();});
  } catch {fail(); ready = Promise.resolve();}
  return Object.freeze({ready, dispose});
}
