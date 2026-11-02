/** Fixed administration routes share the established protected transport and never resend a mutation. */
import {EntryReadError} from '../application/ports';
import type {AdministrationCommandResult, AdministrationOriginal, AdministrationRequest, AdministrationServer} from '../application/administration-ports';
import {administrationCommand} from '../domain/administration-commands';
import type {AdministrationCommand} from '../domain/administration-commands';
import type {JournalContext} from '../domain/journal';
import {administrationCommandBody} from './administration-json';
import * as values from './administration-values';
import {BoundedHTTP, reason} from './http-transport';
import type {FetchTransport} from './http-transport';
import type {EntryEndpoint} from './http-values';
import {assertion, csrf, failure, household} from './http-values';
import {check, fields, identifier, invalid} from './json-values';

function input(value: unknown, lookup: false): AdministrationRequest;
function input(value: unknown, lookup: true): AdministrationOriginal;
function input(value: unknown, lookup: boolean): AdministrationRequest | AdministrationOriginal {
  try {
    const item = fields(value, lookup ? ['key', 'command', 'operationId'] : ['key', 'command'], []);
    const key = identifier(item.key), command = administrationCommand(item.command);
    if (!lookup) return Object.freeze({key, command});
    return Object.freeze({key, command, operationId: item.operationId === null ? null : identifier(item.operationId)});
  } catch {return invalid();}
}
function route(command: AdministrationCommand): string {
  switch (command.action) {
    case 'household.update': return 'household';
    case 'member.update': return 'members/' + command.memberId;
    case 'policy.update': return 'policy';
    case 'member.presentation.update': return 'administration/members/' + command.memberId + '/presentation';
    case 'member.preferences.update': return 'administration/preferences';
  }
}
export class HttpAdministrationServer implements AdministrationServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}
  private read<T>(route: string, expected: JournalContext, decode: (value: unknown) => T, budget: 'standard' | 'roster' = 'standard') {
    return this.network.owned(async signal => decode(await this.network.get(route, expected, signal, budget)));
  }
  capabilities(expected: JournalContext) {return this.read('administration/capabilities', expected, values.capabilities);}
  authorization(expected: JournalContext) {return this.read('authorization', expected, raw => values.authorization(raw, expected));}
  household(expected: JournalContext) {return this.read('household', expected, household);}
  policy(expected: JournalContext) {return this.read('policy', expected, values.policy);}
  roster(expected: JournalContext) {return this.read('administration/roster', expected, values.roster, 'roster');}
  directory(expected: JournalContext) {return this.read('administration/directory', expected, values.directory, 'roster');}
  presentation(memberId: string, expected: JournalContext) {
    return this.network.owned(async signal => {
      const id = identifier(memberId), result = values.presentation(await this.network.get('administration/members/' + id + '/presentation', expected, signal));
      check(result.memberId === id); return result;
    });
  }
  preferences(expected: JournalContext) {return this.read('administration/preferences', expected, values.preferences);}
  original(value: AdministrationOriginal, expected: JournalContext) {
    return this.network.owned(async signal => {
      const original = input(value, true);
      const raw = await this.network.get('administration/requests/' + original.command.action + '/' + original.key, expected, signal);
      return values.receipt(raw, original, 'key');
    });
  }
  operation(value: AdministrationOriginal, expected: JournalContext) {
    return this.network.owned(async signal => {
      const original = input(value, true); check(original.operationId !== null);
      const raw = await this.network.get('operations/' + original.operationId, expected, signal);
      return values.receipt(raw, original, 'operation');
    });
  }
  async send(value: AdministrationRequest, expected: JournalContext): Promise<AdministrationCommandResult> {
    let posted = false;
    return this.network.owned(async signal => {
      let original: AdministrationRequest;
      try {original = input(value, false);}
      catch {return Object.freeze({kind: 'rejected' as const, reason: 'invalid_input' as const, correlationId: null});}
      let token: string;
      try {assertion(expected); token = csrf(await this.network.get('auth/csrf', expected, signal));}
      catch (error) {return Object.freeze({kind: 'rejected' as const, reason: error instanceof EntryReadError ? error.code : 'unavailable' as const, correlationId: null});}
      try {
        const body = administrationCommandBody(original.command);
        if (signal.aborted) throw new EntryReadError('unavailable');
        posted = true;
        const reply = await this.network.request(route(original.command), 'PUT', expected, body, original.key, token, signal);
        if (reply.status === 200) return values.receipt(reply.value, original, 'mutation');
        if ([401,403,409,422,503].includes(reply.status)) return Object.freeze({kind: 'rejected' as const,
          reason: reason(reply.status), correlationId: failure(reply.value)});
      } catch {/* A failed or unbound PUT response cannot establish absence of its effect. */}
      return Object.freeze({kind: 'uncertain' as const});
    }).result.catch(() => posted ? Object.freeze({kind: 'uncertain' as const})
      : Object.freeze({kind: 'rejected' as const, reason: 'unavailable' as const, correlationId: null}));
  }
}
