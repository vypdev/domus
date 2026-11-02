import {EntryReadError} from '../application/ports';
import type {CommandResult, EntryOperation, EntryServer} from '../application/ports';
import type {JournalCommand, JournalContext} from '../domain/journal';
import * as wire from './http-values';
import type {EntryEndpoint} from './http-values';
import {BoundedHTTP, reason, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
export {HTTP_TIMEOUT_MS, HTTP_MAX_BYTES} from './http-transport';
export type {FetchTransport} from './http-transport';

/** Paths are relative to a verified same-origin base; request context asserts, never selects, identity. */
export class HttpEntryServer implements EntryServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}
  session() {return this.network.owned(async signal => {
    const reply = await this.network.request('session', 'GET', null, null, null, null, signal);
    if (reply.status === 401) {wire.failure(reply.value); return null;}
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return wire.session(reply.value, this.network.target);
  });}
  authorization(expected: JournalContext) {return this.network.owned(async signal =>
    wire.authorization(await this.network.get('authorization', expected, signal), expected));}
  household(expected: JournalContext) {return this.network.owned(async signal =>
    wire.household(await this.network.get('household', expected, signal)));}
  operation(action: JournalCommand['action'], operationId: string, expected: JournalContext) {
    return this.network.owned(async signal => {
      const result = wire.receipt(await this.network.get('operations/' + wire.identifier(operationId), expected, signal), action, true) as EntryOperation;
      wire.check(result.operationId === operationId); return result;
    });
  }
  async send(input: JournalCommand & Readonly<{key: string}>, expected: JournalContext): Promise<CommandResult> {
    let posted = false;
    return this.network.owned(async signal => {
      let command: ReturnType<typeof wire.command>, token: string;
      try {
        command = wire.command(input); wire.assertion(expected);
        token = wire.csrf(await this.network.get('auth/csrf', expected, signal));
      } catch (error) {
        return Object.freeze({kind: 'rejected' as const, reason: error instanceof EntryReadError ? error.code : 'unavailable', correlationId: null});
      }
      try {
        if (signal.aborted) throw new EntryReadError('unavailable');
        posted = true;
        const reply = await this.network.request(command.action === 'setup' ? 'household' : 'members/enrollment',
          'POST', expected, JSON.stringify(command.payload), command.key, token, signal);
        if (reply.status === 200) return wire.receipt(reply.value, command.action, false);
        if ([401, 403, 409, 422, 503].includes(reply.status)) return Object.freeze({kind: 'rejected' as const,
          reason: reason(reply.status), correlationId: wire.failure(reply.value)});
      } catch {/* A failed/malformed POST response cannot establish absence of the effect. */}
      return Object.freeze({kind: 'uncertain' as const});
    }).result.catch(() => posted ? Object.freeze({kind: 'uncertain' as const})
      : Object.freeze({kind: 'rejected' as const, reason: 'unavailable' as const, correlationId: null}));
  }
  async logout() {return this.network.owned(async signal => {
    if (this.network.target.deployment === 'native') throw new EntryReadError('forbidden');
    const proof = wire.session(await this.network.get('session', null, signal), this.network.target);
    const token = wire.csrf(await this.network.get('auth/csrf', proof.context, signal));
    const reply = await this.network.request('auth/logout', 'POST', proof.context, '{}', null, token, signal);
    if (reply.status !== 200) readFailure(reply.status, reply.value);
    return wire.logout(reply.value);
  }).result;}
}
