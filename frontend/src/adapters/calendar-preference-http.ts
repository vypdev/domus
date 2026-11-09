/** Preference traffic uses the verified browser context and exact int64 wire values. */
import type {CalendarPreferenceServer, PreferenceRequest, PreferenceScope} from '../application/calendar-preferences';
import {WEEK_STARTS} from '../domain/calendar';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf, failure} from './http-values';
import type {EntryEndpoint} from './http-values';
import {check, choice, fields, identifier, responseRevision} from './json-values';

const BASE = 'tasks/calendar/preferences';

function original(value: unknown, scope: PreferenceScope, request: PreferenceRequest): boolean {
  const receipt = fields(value, ['state','archived_by','operation_id','created_at','result','message','action_required'], []);
  const state = choice(receipt.state, ['committed','historical'] as const);
  check(state === 'historical' ? identifier(receipt.archived_by) : receipt.archived_by === null);
  identifier(receipt.operation_id);
  const result = fields(receipt.result, ['member_id','week_start','revision'], []);
  check(result.member_id === scope.memberId && result.week_start === request.weekStart &&
    BigInt(responseRevision(result.revision)) === BigInt(request.revision) + 1n);
  return true;
}

export class HttpCalendarPreferences implements CalendarPreferenceServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, fetch: FetchTransport) {this.network = new BoundedHTTP(target,fetch);}

  read(scope: PreferenceScope) {
    return this.network.owned(async signal => {
      const row = fields(await this.network.get(BASE,scope.context,signal),['week_start','revision'],[]);
      return {weekStart:choice(row.week_start,WEEK_STARTS),revision:responseRevision(row.revision)};
    });
  }

  send(scope: PreferenceScope, request: PreferenceRequest) {
    return this.network.owned(async signal => {
      const token = csrf(await this.network.get('auth/csrf',scope.context,signal));
      const body = '{"expected_revision":' + request.revision + ',"week_start":' + JSON.stringify(request.weekStart) + '}';
      const response = await this.network.request(BASE,'PUT',scope.context,body,identifier(request.key),token,signal);
      if (response.status === 200) return original(response.value,scope,request);
      if ([401,403,409,422].includes(response.status)) {failure(response.value); return false;}
      throw new Error('calendar_preference_unavailable');
    });
  }

  original(scope: PreferenceScope, request: PreferenceRequest) {
    return this.network.owned(async signal => {
      const response = await this.network.request(BASE + '/requests/' + identifier(request.key),
        'GET',scope.context,null,null,null,signal);
      if (response.status === 200) return original(response.value,scope,request);
      if (response.status === 404) {
        failure(response.value);
        if ((response.value as {code: unknown}).code === 'operation_missing') return false;
      }
      throw new Error('calendar_preference_unavailable');
    });
  }
}
