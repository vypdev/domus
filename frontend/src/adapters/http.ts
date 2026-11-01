import {EntryReadError} from '../application/ports';
import type {CommandResult, EntryOperation, EntryRead, EntryServer, ReadFault} from '../application/ports';
import type {JournalCommand, JournalContext} from '../domain/journal';
import * as wire from './http-values';
import type {EntryEndpoint} from './http-values';

export const HTTP_TIMEOUT_MS = 15_000;
export const HTTP_MAX_BYTES = 65_536;
export type FetchTransport = (path: string, init: RequestInit) => Promise<Response>;
function reason(status: number): ReadFault | 'conflict' | 'invalid_input' {
  switch (status) {
    case 401: return 'authentication_required';
    case 403: return 'forbidden';
    case 409: return 'conflict';
    case 422: return 'invalid_input';
    default: return 'unavailable';
  }
}
function readFailure(status: number, value: unknown): never {
  wire.failure(value); const code = reason(status);
  throw new EntryReadError(code === 'conflict' || code === 'invalid_input' ? 'invalid_response' : code);
}
async function consume(response: Response, expectedURL: string, signal: AbortSignal): Promise<unknown> {
  wire.check(response.body !== null); const reader = response.body.getReader();
  const abort = () => {void reader.cancel().catch(() => {});};
  signal.addEventListener('abort', abort, {once: true});
  let complete = false;
  try {
    wire.check(!response.redirected && response.url === expectedURL
      && !['opaque', 'opaqueredirect', 'error'].includes(response.type));
    wire.check(/^application\/json(?:\s*;\s*charset=utf-8)?$/iu.test(response.headers.get('Content-Type') ?? '')
      && /(?:^|,)\s*no-store\s*(?:,|$)/iu.test(response.headers.get('Cache-Control') ?? ''));
    const length = response.headers.get('Content-Length');
    wire.check(length === null || (/^\d+$/u.test(length) && Number(length) <= HTTP_MAX_BYTES));
    const decoder = new TextDecoder('utf-8', {fatal: true}); let bytes = 0, raw = '';
    while (true) {
      if (signal.aborted) throw new EntryReadError('unavailable');
      const part = await reader.read();
      if (signal.aborted) throw new EntryReadError('unavailable');
      if (part.done) break;
      bytes += part.value.byteLength; wire.check(bytes <= HTTP_MAX_BYTES);
      raw += decoder.decode(part.value, {stream: true});
    }
    raw += decoder.decode(); complete = true; return wire.wireJSON(raw);
  } finally {
    signal.removeEventListener('abort', abort);
    if (!complete) {try {await reader.cancel();} catch {/* Retain the bounded original failure. */}}
    reader.releaseLock();
  }
}

/** Paths are relative to a verified same-origin base; request context asserts, never selects, identity. */
export class HttpEntryServer implements EntryServer {
  private readonly target: EntryEndpoint;
  constructor(target: EntryEndpoint, private readonly transport: FetchTransport) {this.target = wire.endpoint(target);}
  private owned<T>(work: (signal: AbortSignal) => Promise<T>): EntryRead<T> {
    const controller = new AbortController();
    let rejectAbort!: (error: EntryReadError) => void;
    const interrupted = new Promise<never>((_resolve, reject) => {rejectAbort = reject;});
    const cancel = () => {controller.abort(); rejectAbort(new EntryReadError('unavailable'));};
    const timer = setTimeout(cancel, HTTP_TIMEOUT_MS);
    const result = (async () => {
      try {return await Promise.race([work(controller.signal), interrupted]);}
      catch (error) {throw error instanceof EntryReadError ? error : new EntryReadError('unavailable');}
      finally {clearTimeout(timer);}
    })();
    return {result, cancel};
  }
  private async request(route: string, method: 'GET' | 'POST', expected: JournalContext | null,
    body: string | null, key: string | null, token: string | null, signal: AbortSignal) {
    if (signal.aborted) throw new EntryReadError('unavailable');
    const path = this.target.applicationBase + 'api/v1/' + route;
    const headers = new Headers({'Accept': 'application/json'});
    if (expected !== null) headers.set('X-Domus-Context', wire.assertion(expected));
    if (body !== null) headers.set('Content-Type', 'application/json');
    if (token !== null) headers.set('X-CSRF-Token', token);
    if (key !== null) headers.set('Idempotency-Key', key);
    const transport = this.transport;
    const response = await transport(path, {method, headers, body, signal,
      mode: 'same-origin', credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer'});
    const value = await consume(response, this.target.origin + path, signal);
    return {status: response.status, value};
  }
  private async get(route: string, expected: JournalContext | null, signal: AbortSignal) {
    const reply = await this.request(route, 'GET', expected, null, null, null, signal);
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return reply.value;
  }
  session() {return this.owned(async signal => {
    const reply = await this.request('session', 'GET', null, null, null, null, signal);
    if (reply.status === 401) {wire.failure(reply.value); return null;}
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return wire.session(reply.value, this.target);
  });}
  authorization(expected: JournalContext) {return this.owned(async signal =>
    wire.authorization(await this.get('authorization', expected, signal), expected));}
  household(expected: JournalContext) {return this.owned(async signal =>
    wire.household(await this.get('household', expected, signal)));}
  operation(action: JournalCommand['action'], operationId: string, expected: JournalContext) {
    return this.owned(async signal => {
      const result = wire.receipt(await this.get('operations/' + wire.identifier(operationId), expected, signal), action, true) as EntryOperation;
      wire.check(result.operationId === operationId); return result;
    });
  }
  async send(input: JournalCommand & Readonly<{key: string}>, expected: JournalContext): Promise<CommandResult> {
    let posted = false;
    return this.owned(async signal => {
      let command: ReturnType<typeof wire.command>, token: string;
      try {
        command = wire.command(input); wire.assertion(expected);
        token = wire.csrf(await this.get('auth/csrf', expected, signal));
      } catch (error) {
        return Object.freeze({kind: 'rejected' as const, reason: error instanceof EntryReadError ? error.code : 'unavailable', correlationId: null});
      }
      try {
        if (signal.aborted) throw new EntryReadError('unavailable');
        posted = true;
        const reply = await this.request(command.action === 'setup' ? 'household' : 'members/enrollment',
          'POST', expected, JSON.stringify(command.payload), command.key, token, signal);
        if (reply.status === 200) return wire.receipt(reply.value, command.action, false);
        if ([401, 403, 409, 422, 503].includes(reply.status)) return Object.freeze({kind: 'rejected' as const,
          reason: reason(reply.status), correlationId: wire.failure(reply.value)});
      } catch {/* A failed/malformed POST response cannot establish absence of the effect. */}
      return Object.freeze({kind: 'uncertain' as const});
    }).result.catch(() => posted ? Object.freeze({kind: 'uncertain' as const})
      : Object.freeze({kind: 'rejected' as const, reason: 'unavailable' as const, correlationId: null}));
  }
  async logout() {return this.owned(async signal => {
    if (this.target.deployment === 'native') throw new EntryReadError('forbidden');
    const proof = wire.session(await this.get('session', null, signal), this.target);
    const token = wire.csrf(await this.get('auth/csrf', proof.context, signal));
    const reply = await this.request('auth/logout', 'POST', proof.context, '{}', null, token, signal);
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return wire.logout(reply.value);
  }).result;}
}
