/** Shared same-origin, bounded-stream transport; semantic clients own all routes and effects. */
import {EntryReadError} from '../application/ports';
import type {EntryRead, ReadFault} from '../application/ports';
import type {JournalContext} from '../domain/journal';
import * as wire from './http-values';
import type {EntryEndpoint} from './http-values';
import {administrationJSON, ROSTER_MAX_BYTES} from './json-values';

export const HTTP_TIMEOUT_MS = 15_000;
export const HTTP_MAX_BYTES = 65_536;
export type FetchTransport = (path: string, init: RequestInit) => Promise<Response>;
export function reason(status: number): ReadFault | 'conflict' | 'invalid_input' {
  switch (status) {
    case 401: return 'authentication_required';
    case 403: return 'forbidden';
    case 409: return 'conflict';
    case 422: return 'invalid_input';
    default: return 'unavailable';
  }
}
export function readFailure(status: number, value: unknown): never {
  wire.failure(value); const code = reason(status);
  throw new EntryReadError(code === 'conflict' || code === 'invalid_input' ? 'invalid_response' : code);
}
async function consume(response: Response, expectedURL: string, signal: AbortSignal, maximumBytes: 65536 | 1048576): Promise<unknown> {
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
    wire.check(length === null || (/^\d+$/u.test(length) && Number(length) <= maximumBytes));
    const decoder = new TextDecoder('utf-8', {fatal: true}); let bytes = 0, raw = '';
    while (true) {
      if (signal.aborted) throw new EntryReadError('unavailable');
      const part = await reader.read();
      if (signal.aborted) throw new EntryReadError('unavailable');
      if (part.done) break;
      bytes += part.value.byteLength; wire.check(bytes <= maximumBytes);
      raw += decoder.decode(part.value, {stream: true});
    }
    raw += decoder.decode(); complete = true; return administrationJSON(raw, maximumBytes);
  } finally {
    signal.removeEventListener('abort', abort);
    if (!complete) {try {await reader.cancel();} catch {/* Retain the bounded original failure. */}}
    reader.releaseLock();
  }
}

export class BoundedHTTP {
  readonly target: EntryEndpoint;
  constructor(target: EntryEndpoint, private readonly transport: FetchTransport) {this.target = wire.endpoint(target);}
  owned<T>(work: (signal: AbortSignal) => Promise<T>): EntryRead<T> {
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
  async request(route: string, method: 'GET' | 'POST' | 'PUT', expected: JournalContext | null,
    body: string | null, key: string | null, token: string | null, signal: AbortSignal, budget: 'standard' | 'roster' = 'standard') {
    if (signal.aborted) throw new EntryReadError('unavailable');
    wire.check(budget === 'standard' || budget === 'roster');
    const maximumBytes = budget === 'roster' ? ROSTER_MAX_BYTES : HTTP_MAX_BYTES;
    const path = this.target.applicationBase + 'api/v1/' + route;
    const headers = new Headers({'Accept': 'application/json'});
    if (expected !== null) headers.set('X-Domus-Context', wire.assertion(expected));
    if (body !== null) headers.set('Content-Type', 'application/json');
    if (token !== null) headers.set('X-CSRF-Token', token);
    if (key !== null) headers.set('Idempotency-Key', key);
    const transport = this.transport;
    const response = await transport(path, {method, headers, body, signal,
      mode: 'same-origin', credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer'});
    const value = await consume(response, this.target.origin + path, signal, maximumBytes);
    return {status: response.status, value};
  }
  async get(route: string, expected: JournalContext | null, signal: AbortSignal, budget: 'standard' | 'roster' = 'standard') {
    const reply = await this.request(route, 'GET', expected, null, null, null, signal, budget);
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return reply.value;
  }
}
