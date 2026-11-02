import {expect, test, vi} from 'vitest';
import {HttpEntryServer} from '../src/adapters/http';
import type {JournalContext} from '../src/domain/journal';
import {wireJSON} from '../src/adapters/http-values';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const revisions = ['1', '9007199254740991', '9007199254740992', '9007199254740993', '9223372036854775807'];
function fixture(deployment: 'native' | 'standalone', raw: string) {
  const applicationBase = deployment === 'native' ? '/api/hassio_ingress/' + 'b'.repeat(43) + '/' : '/';
  const endpoint = {deployment, applicationBase, origin: 'https://domus.example'};
  const transport = vi.fn(async (path: string, _init: RequestInit) => {
    const response = new Response(raw, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    Object.defineProperty(response, 'url', {value: endpoint.origin + path}); return response;
  });
  return {transport, server: new HttpEntryServer(endpoint, transport)};
}
function access(revision: string) {
  return '{"state":"active","setup_allowed":false,"enrollment_allowed":false,'
    + '"permission_scope":"household_administration","permissions":["household.read"],'
    + '"member":{"member_id":"member-1","role":"viewer","status":"active","revision":' + revision
    + ',"ha_user_id":"' + context.subject + '","exceptions":[]},"policy_revision":' + revision
    + ',"effective_role":"administrator","message":"Current access.","action_required":"No action required."}';
}

for (const deployment of ['native', 'standalone'] as const) {
  test.each(revisions)(`${deployment}: household revision %s remains exact after a real response stream`, async revision => {
    const f = fixture(deployment, '{"household_id":"home","name":"Home","time_zone":"UTC","revision":' + revision + '}');
    expect((await f.server.household(context).result).revision).toBe(revision);
    expect(f.transport).toHaveBeenCalledTimes(1);
    const init = f.transport.mock.calls[0][1];
    expect(init.method).toBe('GET'); expect(init.body).toBeNull();
    expect(new Headers(init.headers).get('X-Domus-Context')).toBe(`v1:${context.installationId}:edge:${context.subject}`);
  });
  test.each(revisions)(`${deployment}: high member/policy revision %s cannot make actual authorization unavailable`, async revision => {
    const f = fixture(deployment, access(revision));
    expect(await f.server.authorization(context).result).toMatchObject({state: 'active', permissions: ['household.read']});
    expect(f.transport).toHaveBeenCalledTimes(1);
  });
  test(`${deployment}: enrollment original receipt preserves a high policy revision without changing delivery or issuing a write`, async () => {
    const raw = '{"state":"committed","archived_by":null,"operation_id":"op-1","created_at":1000,'
      + '"result":{"member_id":"member-1","status":"pending","role":"viewer","revision":1,'
      + '"policy_revision":9223372036854775807},"delivery":"pending","message":"Linked.","action_required":"Review."}';
    const f = fixture(deployment, raw);
    expect(await f.server.operation('enroll', 'op-1', context).result).toMatchObject({delivery: 'pending',
      result: {revision: '1', policy_revision: '9223372036854775807'}});
    expect(f.transport.mock.calls[0][1].method).toBe('GET');
    expect(new Headers(f.transport.mock.calls[0][1].headers).has('X-CSRF-Token')).toBe(false);
  });
}

test.each(['"1"', '"9007199254740993"', '{"source":"1"}', 'null', 'true', '0', '-1',
  '1.0', '1e0', '9223372036854775808'])(
  'a forged/inexact/out-of-range revision source %s cannot become current facts', async revision => {
    const f = fixture('standalone', access(revision));
    await expect(f.server.authorization(context).result).rejects.toThrow('invalid_response');
  });

test('the retained safe-number JSON helper keeps its own strict contract independently of exact revision transport', () => {
  expect(wireJSON('{"value":12345}')).toEqual({value: 12345});
  expect(() => wireJSON('{"value":9007199254740993}')).toThrow('invalid_response');
});

test('legitimate backend Unicode household text is not rejected by JavaScript trim differences', async () => {
  const f = fixture('standalone', '{"household_id":"home","name":"\\ufeff","time_zone":"UTC","revision":1}');
  expect((await f.server.household(context).result).name).toBe('\uFEFF');
});
