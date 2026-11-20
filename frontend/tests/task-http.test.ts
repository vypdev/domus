import {afterEach, expect, test, vi} from 'vitest';
import {HTTP_TIMEOUT_MS} from '../src/adapters/http-transport';
import {HttpTaskServer} from '../src/adapters/task-http';
import {taskCommand} from '../src/domain/tasks';
import {revisionValue} from '../src/domain/administration';
import type {TaskCommand} from '../src/domain/tasks';
import type {JournalContext} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge', subject: 'a'.repeat(32)};
const REV = '9007199254740993', NEXT = '9007199254740994';
const rules = {claim_allowed: true, eligible_roles: ['administrator', 'adult', 'restricted'], verification: 'role_default',
  adult_performer_may_approve: true, task_scoped_material_consumption: true, material_recording: 'review_on_completion', point_value_minor: 0, dependency_gate: 'performed'};
const summary = () => ({occurrence_id: 'work-1', definition_id: 'definition-1', definition_revision: 1,
  title: '<b>Clean 🧹</b>', state: 'available', revision: '$revision', assignee_ids: [], due_at: null, current_cycle_id: null});
const cycle = () => ({cycle_id: 'cycle-1', household_id: 'home', occurrence_id: 'work-1', recorded_by: 'member-1',
  performers: [{member_id: 'member-1', role: 'adult'}], rules, definition_revision: 1, task_policy_revision: 1,
  identity_policy_revision: 1, performed_at: '$revision', recorded_at: '$revision', verification: 'none', verified_by: null,
  verified_at: null, verification_reason: '', closed_at: null, revision: 1});
const detail = () => ({work: {occurrence_id: 'work-1', household_id: 'home', definition_snapshot: {definition_id: 'definition-1', household_id: 'home',
  content: {title: '<b>Clean 🧹</b>', description: 'Wipe\nthen dry', priority: 'normal', tags: []}, created_at: 100, overrides: {}, state: 'active', revision: 1, materials: []},
  created_at: 100, state: 'available', revision: '$revision', assignee_ids: [], prerequisite_ids: [], required_subtask_ids: [], due_at: null,
  current_cycle_id: null, current_cycle_revision: null, state_reason: ''}, rules, task_policy_revision: 1, requirements: [], cycle: null as null | ReturnType<typeof cycle>,
  allowed_actions: ['claim', 'complete', 'assign', 'dependencies.update', 'transition:in_progress'], consumer_delivery: 'unconfirmed', materials: [],
  dependency_reviews: {items: [], next_cursor: null}, dependency_review_required: false});
const rawCommands = [
  {action: 'task.create', payload: {expected_revision: 0, title: '  Clean 🧹  ', description: '', priority: 'normal'}},
  {action: 'task.claim', occurrenceId: 'work-1', payload: {expected_revision: REV}},
  {action: 'task.complete', occurrenceId: 'work-1', payload: {expected_revision: REV, performer_ids: ['member-1'], performed_at: REV, material_usages: null}},
  {action: 'task.verify', occurrenceId: 'work-1', payload: {expected_revision: REV, cycle_id: 'cycle-1', decision: 'approved', reason: ''}},
  {action: 'task.reopen', occurrenceId: 'work-1', payload: {expected_revision: REV, cycle_id: 'cycle-1', reason: 'Repeat work'}},
];
const commands = rawCommands.map(raw => {const value = taskCommand(raw); if (!value) throw Error('invalid test command'); return value;});
const paths = ['definitions', 'occurrences/work-1/claim', 'occurrences/work-1/complete', 'occurrences/work-1/verify', 'occurrences/work-1/reopen'];
function receipt(index: number, lookup = false) {
  return {state: 'committed', archived_by: null, operation_id: 'op-1', created_at: 100, message: 'Saved.', action_required: 'Review.',
    result: {definition_id: 'definition-1', definition_revision: 1, occurrence_id: 'work-1', revision: index === 0 ? 1 : '$next',
      state: index === 2 || index === 3 ? 'completed' : 'assigned', assignee_ids: ['member-1'], state_reason: '', prerequisite_ids: [], required_subtask_ids: [],
      ...(index >= 2 ? {cycle: {...cycle(), verification: index === 3 ? 'approved' : 'none'}, consumer_delivery: 'unconfirmed'} : {}),
      ...(index === 4 ? {compensates_cycle_id: 'cycle-1', dependency_review_required: true} : {})},
    ...(lookup ? {action: commands[index].action, command_key: 'original-key', delivery: 'pending'} : {})};
}
function encode(value: unknown) {return JSON.stringify(value).replaceAll('"$revision"', REV).replaceAll('"$next"', NEXT);}
function reply(value: unknown, status = 200) {return new Response(encode(value), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});}
const failure = (status: number, code = 'request_forbidden') => reply({state: 'blocked', code, message: 'Private server detail.', action_required: 'Review.', correlation_id: 'cor_safe'}, status);
function fixture(mode: 'native' | 'standalone' = 'standalone') {
  const target = {deployment: mode, applicationBase: mode === 'native' ? '/api/hassio_ingress/' + 'b'.repeat(43) + '/' : '/', origin: 'https://domus.example'};
  const transport = vi.fn(async (_path: string, _init: RequestInit): Promise<Response> => reply({}));
  const network = async (path: string, init: RequestInit) => {const value = await transport(path, init);
    if (!value.url) Object.defineProperty(value, 'url', {value: target.origin + path}); return value;};
  return {target, transport, server: new HttpTaskServer(target, network)};
}

function materialReceipt(action = 'post', quantity = '2') {
  const corrected=action==='correct',effectRevision=corrected?2:1;
  return {...receipt(2), result:{...receipt(2).result, revision:'$revision', material_action:action,
    material:{intent_id:'intent-1',cycle_id:'cycle-1',line_id:'line-1',revision:corrected&&quantity!=='0'?9:8,effect_revision:effectRevision,
      submitted_quantity:corrected?null:quantity, quantity, state:quantity==='0'?'not_used':corrected?'corrected':'posted',
      pending_reason:null,movement_id:quantity==='0'?null:'movement-1',message:'Saved.',action_required:null,
      confirmed_quantity:quantity==='0'?null:quantity,confirmed_effect_revision:quantity==='0'?null:effectRevision,posted_at:quantity==='0'?null:100},
    material_source:{household_id:'home',occurrence_id:'work-1',cycle_id:'cycle-1',intent_id:'intent-1',line_id:'line-1',
      definition_revision:1,performer_ids:['member-1']}}};
}
test.each(['native','standalone'] as const)('%s material post and initial zero recording bind original identities without inventing a task revision', async mode => {
  const f=fixture(mode);
  for (const action of ['post','correct'] as const) {
    const payload=action==='post'?{action,reason:''}:{action,reason:'Unused <soap>',quantity:'0'};
    const command=taskCommand({action:'task.material.settle',occurrenceId:'work-1',intentId:'intent-1',
      payload:{expected_revision:'7',cycle_id:'cycle-1',...payload}})!;
    const request={key:'original-key',command}, raw=materialReceipt(action,action==='post'?'2':'0');
    f.transport.mockResolvedValueOnce(reply({csrf_token:'a'.repeat(64)})).mockResolvedValueOnce(reply(raw));
    const saved=await f.server.send(request,context);
    expect(saved).toMatchObject({kind:'receipt',action:'task.material.settle',intentId:'intent-1',material:{revision:'8',quantity:action==='post'?'2':'0'}});
    expect(saved).toMatchObject({material:{effectRevision:action==='correct'?'2':'1'}});
    expect(saved).not.toHaveProperty('revision'); expect(saved).not.toHaveProperty('state');
    const [path,init]=f.transport.mock.calls.at(-1)!;
    expect(path).toBe(f.target.applicationBase+'api/v1/tasks/occurrences/work-1/materials/intent-1/settlement');
    expect(init.method).toBe('POST'); expect(JSON.parse(String(init.body))).toEqual({expected_revision:7,cycle_id:'cycle-1',...payload});
    f.transport.mockResolvedValueOnce(reply({...raw,action:'task.material.settle',command_key:'original-key',delivery:'pending'}));
    expect(await f.server.original({...request,operationId:'op-1'},context).result).toMatchObject({operationId:'op-1'});
    expect(f.transport.mock.calls.at(-1)![1].method).toBe('GET');
    expect(f.transport.mock.calls.at(-1)![0]).toBe(f.target.applicationBase+'api/v1/tasks/requests/task.material.settle/original-key');
  }
});
test.each(['matching','intent','cycle','line','revision','scope_occurrence','scope_cycle','scope_intent','scope_line','definition','performers','home','cycle_definition','action','consumer','quantity'])(
  'a material correction receipt validates the %s case against the original command', async kind => {
    const f=fixture(), raw=materialReceipt('correct');
    const request={key:'original-key',command:taskCommand({action:'task.material.settle',occurrenceId:'work-1',intentId:'intent-1',
      payload:{expected_revision:'7',cycle_id:'cycle-1',action:'correct',quantity:'2',reason:'Initial actual use'}})!};
    const value=raw.result;
    if(kind==='intent')value.material.intent_id='other';
    if(kind==='cycle')value.material.cycle_id='other';
    if(kind==='line')value.material.line_id='other';
    if(kind==='revision')value.material.revision=6;
    if(kind==='scope_occurrence')value.material_source.occurrence_id='other';
    if(kind==='scope_cycle')value.material_source.cycle_id='other';
    if(kind==='scope_intent')value.material_source.intent_id='other';
    if(kind==='scope_line')value.material_source.line_id='other';
    if(kind==='definition')value.material_source.definition_revision=2;
    if(kind==='performers')value.material_source.performer_ids=['other'];
    if(kind==='home')value.material_source.household_id='other';
    if(kind==='cycle_definition')value.cycle!.definition_revision=2;
    if(kind==='action')value.material_action='post';
    if(kind==='consumer')value.consumer_delivery='confirmed';
    if(kind==='quantity')value.material.quantity='3';
    f.transport.mockResolvedValueOnce(reply({csrf_token:'a'.repeat(64)})).mockResolvedValueOnce(reply(raw));
    const result=await f.server.send(request,context);
    if(kind==='matching')expect(result).toMatchObject({kind:'receipt',material:{revision:'9',effectRevision:'2',submittedQuantity:null,quantity:'2',state:'corrected'}});
    else expect(result).toEqual({kind:'uncertain'});
    expect(f.transport).toHaveBeenCalledTimes(2);
  });
test('the current linking hint is an explicit server boolean and malformed outcome quantities are rejected', async () => {
  const f=fixture();
  for(const can_link_materials of [true,false]) {
    f.transport.mockResolvedValueOnce(reply({household_id:'home',member_id:'member-1',can_create:true,can_link_materials}));
    expect((await f.server.access(context).result).canLinkMaterials).toBe(can_link_materials);
  }
  const request={key:'original-key',command:taskCommand({action:'task.material.settle',occurrenceId:'work-1',intentId:'intent-1',
    payload:{expected_revision:'7',cycle_id:'cycle-1',action:'post',reason:''}})!};
  const raw=materialReceipt(); raw.result.material.quantity='1.0';
  f.transport.mockResolvedValueOnce(reply({...raw,action:'task.material.settle',command_key:'original-key',delivery:'pending'}));
  await expect(f.server.original({...request,operationId:null},context).result).rejects.toThrow('invalid_response');
});
afterEach(() => vi.useRealTimers());

test.each((['native', 'standalone'] as const).flatMap(mode =>
  (['in_progress', 'blocked', 'assigned', 'available'] as const).map(target => ({mode, target}))))(
  '$mode progress to $target binds its exact original state and reason', async ({mode, target}) => {
    const f = fixture(mode);
    const reason = target === 'blocked' ? 'Waiting for parts\n🧰' : '';
    const command = taskCommand({action: 'task.transition', occurrenceId: 'work-1',
      payload: {expected_revision: REV, target, reason}})!;
    const request = {key: 'progress-key', command};
    const saved = {...receipt(1), result: {...receipt(1).result,
      state: target, state_reason: reason, assignee_ids: target === 'available' ? [] : ['member-1']}};
    f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(saved));
    expect(await f.server.send(request, context)).toMatchObject({
      kind: 'receipt', action: 'task.transition', revision: NEXT, state: target, stateReason: reason});
    const [path, init] = f.transport.mock.calls[1];
    expect(path).toBe(f.target.applicationBase + 'api/v1/tasks/occurrences/work-1/transition');
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"expected_revision":' + REV + ',"target":' + JSON.stringify(target)
      + ',"reason":' + JSON.stringify(reason) + '}');
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('progress-key');
    f.transport.mockResolvedValueOnce(reply({...saved,
      action: 'task.transition', command_key: 'progress-key', delivery: 'pending'}));
    expect(await f.server.original({...request, operationId: 'op-1'}, context).result)
      .toMatchObject({kind: 'receipt', state: target, stateReason: reason});
    expect(f.transport.mock.calls[2][0]).toBe(f.target.applicationBase
      + 'api/v1/tasks/requests/task.transition/progress-key');
  });

test.each([
  {state: 'in_progress'},
  {state_reason: 'A different reason'},
  {occurrence_id: 'another-task'},
  {revision: REV},
])('a progress receipt with a different bound fact %# remains uncertain', async changes => {
  const f = fixture();
  const command = taskCommand({action: 'task.transition', occurrenceId: 'work-1',
    payload: {expected_revision: REV, target: 'blocked', reason: 'Waiting'}})!;
  const saved = {...receipt(1), result: {...receipt(1).result, state: 'blocked', state_reason: 'Waiting', ...changes}};
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(saved));
  expect(await f.server.send({key: 'progress-key', command}, context)).toEqual({kind: 'uncertain'});
  f.transport.mockResolvedValueOnce(reply({...saved,
    action: 'task.transition', command_key: 'progress-key', delivery: 'pending'}));
  await expect(f.server.original({key: 'progress-key', command, operationId: 'op-1'}, context).result)
    .rejects.toThrow('invalid_response');
});

test('task detail preserves the exact current blocking reason', async () => {
  const f = fixture();
  const raw = detail();
  raw.work.state = 'blocked';
  raw.work.state_reason = 'Waiting for <parts>\n🧰';
  f.transport.mockResolvedValueOnce(reply(raw));
  expect(await f.server.detail('work-1', 'home', context).result)
    .toMatchObject({state: 'blocked', stateReason: raw.work.state_reason});
});

test.each([null, 1, '', ' \n\t', '\u0000Invalid', '\ud800', '🧰'.repeat(1001)])(
  'invalid current blocking reason %# is rejected', async state_reason => {
    const f = fixture();
    const raw = detail();
    f.transport.mockResolvedValueOnce(reply({...raw, work: {...raw.work, state: 'blocked', state_reason}}));
    await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
  });

test.each(['native', 'standalone'] as const)('%s assignment uses PUT and binds the original assignee set', async mode => {
  const f = fixture(mode);
  const command = taskCommand({action: 'task.assign', occurrenceId: 'work-1',
    payload: {expected_revision: REV, assignee_ids: ['member-2', 'member-1']}})!;
  const request = {key: 'assignment-key', command};
  const saved = {...receipt(1), result: {...receipt(1).result, assignee_ids: ['member-1', 'member-2']}};
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(saved));
  expect(await f.server.send(request, context)).toMatchObject({kind: 'receipt', action: 'task.assign',
    revision: NEXT, assigneeIds: ['member-1', 'member-2']});
  const [path, init] = f.transport.mock.calls[1];
  expect(path).toBe(f.target.applicationBase + 'api/v1/tasks/occurrences/work-1/assignment');
  expect(init.method).toBe('PUT');
  expect(init.body).toBe('{"expected_revision":' + REV + ',"assignee_ids":["member-2","member-1"]}');
  expect(new Headers(init.headers).get('Idempotency-Key')).toBe('assignment-key');
  const original = {...saved, action: 'task.assign', command_key: 'assignment-key', delivery: 'pending'};
  f.transport.mockResolvedValueOnce(reply(original));
  expect(await f.server.original({...request, operationId: 'op-1'}, context).result)
    .toMatchObject({kind: 'receipt', assigneeIds: ['member-1', 'member-2']});
  expect(f.transport.mock.calls[2][0]).toBe(f.target.applicationBase + 'api/v1/tasks/requests/task.assign/assignment-key');
  f.transport.mockResolvedValueOnce(reply({...original, result: {...saved.result, assignee_ids: ['member-1']}}));
  await expect(f.server.original({...request, operationId: 'op-1'}, context).result).rejects.toThrow('invalid_response');
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply({...saved,
    result: {...saved.result, assignee_ids: ['member-1']}}));
  expect(await f.server.send(request, context)).toEqual({kind: 'uncertain'});
});

test('assignment release confirms an empty assignee set', async () => {
  const f = fixture();
  const command = taskCommand({action: 'task.assign', occurrenceId: 'work-1', payload: {expected_revision: REV, assignee_ids: []}})!;
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply({...receipt(1),
    result: {...receipt(1).result, state: 'available', assignee_ids: []}}));
  expect(await f.server.send({key: 'release-key', command}, context))
    .toMatchObject({kind: 'receipt', state: 'available', assigneeIds: []});
});

test.each([
  [403, 'task_assignee_denied', true, 'assignees_unavailable'],
  [403, 'permission_denied', true, 'forbidden'],
  [422, 'task_assignee_denied', true, 'invalid_input'],
  [403, 'task_assignee_denied', false, 'forbidden'],
] as const)('assignment rejection %s/%s retains only its safe semantic outcome', async (status, code, assignment, expected) => {
  const f = fixture();
  const command = assignment ? taskCommand({action: 'task.assign', occurrenceId: 'work-1',
    payload: {expected_revision: REV, assignee_ids: ['member-1']}})! : commands[0];
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(failure(status, code));
  expect(await f.server.send({key: 'selection-key', command}, context))
    .toEqual({kind: 'rejected', reason: expected, correlationId: 'cor_safe'});
});

test.each(['fixed', 'relative'] as const)('scheduled %s task uses exact policy and recovers the original operation', async kind => {
  const f = fixture();
  const rawPolicy = {zone: 'Europe/Madrid', data_identity: 'tzdata:2026.6/iana:2026f',
    repeated_time: 'second_instant', revision: '$revision'};
  f.transport.mockResolvedValueOnce(reply({household_id: 'home', member_id: 'member-1', can_create: true, schedule_policy: rawPolicy}));
  const access = await f.server.access(context).result;
  expect(access.schedulePolicy?.revision).toBe(REV);
  const start = kind === 'fixed' ? {kind: 'time', local: '2027-01-02T09:30'} : {kind: 'date', local: '2027-01-02'};
  const rule = kind === 'fixed' ? {rrule: 'FREQ=WEEKLY;BYDAY=SA'} : {interval_days: 17, visibility: 'at_verification'};
  const command = taskCommand({action: 'task.create', payload: {expected_revision: 0, title: 'Inspect filter', description: '', priority: 'normal',
    materials:[{reference_id:'product-reference',planned_quantity:'1.25'}],
    overrides: {point_value_minor: 225}, schedule: {draft: {kind, start, ...rule}, policy: access.schedulePolicy}}})!;
  const request = {key: 'scheduled-request', command};
  const raw = {state: 'committed', archived_by: null, operation_id: 'scheduled-op', created_at: 100,
    message: 'Saved.', action_required: 'Review.', result: {definition_id: 'definition-1', schedule_id: 'rule-1',
      revision: 1, pattern_revision: 1, processing: 'pending', state: 'active', first_occurrence_id: null, point_value_minor: 225}};
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'a'.repeat(64)})).mockResolvedValueOnce(reply(raw));
  expect(await f.server.send(request, context)).toMatchObject({kind: 'receipt', occurrenceId: null, state: 'active', basePointsMinor: 225});
  const [path, init] = f.transport.mock.calls[2];
  expect(path).toBe('/api/v1/tasks/recurrence/creation/' + kind);
  expect(init.body).toBe(encode({task: {title: 'Inspect filter', description: '', priority: 'normal', overrides: {point_value_minor: 225},
    materials:[{reference_id:'product-reference',planned_quantity:'1.25'}]},
    start, ...rule, policy: rawPolicy}));
  f.transport.mockResolvedValueOnce(reply({...raw, action: 'recurrence.' + kind + '.create', command_key: request.key, delivery: 'pending'}));
  expect(await f.server.original({...request, operationId: null}, context).result).toMatchObject({operationId: 'scheduled-op'});
  expect(f.transport.mock.calls.at(-1)?.[0]).toBe('/api/v1/tasks/recurrence/creation/requests/recurrence.' + kind + '.create/' + request.key);
  for (const change of [{revision: 2}, {pattern_revision: 2}, {state: 'paused'}, {processing: 'current'}, {first_occurrence_id: 'invented'}]) {
    f.transport.mockResolvedValueOnce(reply({...raw, result: {...raw.result, ...change},
      action: 'recurrence.' + kind + '.create', command_key: request.key, delivery: 'pending'}));
    await expect(f.server.original({...request, operationId: null}, context).result).rejects.toThrow();
  }
});

test.each([0, 225])('creation and original recovery bind the exact configured amount %s', async amount => {
  const f = fixture();
  const overrides = {point_value_minor: amount};
  const command = taskCommand({...rawCommands[0], payload: {...rawCommands[0].payload, overrides}})!;
  const request = {key: 'original-key', command};
  const raw = receipt(0);
  f.transport.mockResolvedValueOnce(reply({csrf_token: 'a'.repeat(64)}))
    .mockResolvedValueOnce(reply({...raw, result: {...raw.result, ...overrides}}));
  expect(await f.server.send(request, context)).toMatchObject({kind: 'receipt', basePointsMinor: amount});
  expect(JSON.parse(String(f.transport.mock.calls[1][1].body))).toMatchObject({overrides});
  const original = receipt(0, true);
  f.transport.mockResolvedValueOnce(reply({...original, result: {...original.result, ...overrides}}));
  expect(await f.server.original({...request, operationId: 'op-1'}, context).result).toMatchObject({basePointsMinor: amount});
  for (const result of [original.result, {...original.result, point_value_minor: amount + 1}]) {
    f.transport.mockResolvedValueOnce(reply({...original, result}));
    await expect(f.server.original({...request, operationId: 'op-1'}, context).result).rejects.toThrow('invalid_response');
  }
});

for (const mode of ['native', 'standalone'] as const) {
  test(`${mode}: list/detail project literal text and exact values, with server-owned allowed actions`, async () => {
    const f = fixture(mode); f.transport.mockResolvedValueOnce(reply({items: [summary()], next_cursor: 'cursor/+?'})).mockResolvedValueOnce(reply(detail()));
    const page = await f.server.list(context, null).result;
    expect(page.items[0]).toMatchObject({title: '<b>Clean 🧹</b>', revision: REV, dueAt: null}); expect(page.nextCursor).toBe('cursor/+?');
    const work = await f.server.detail('work-1', 'home', context).result;
    expect(work).toMatchObject({description: 'Wipe\nthen dry', allowedActions: ['claim', 'complete', 'assign', 'dependencies.update', 'transition:in_progress'], cycle: null});
    expect(Object.isFrozen(work)).toBe(true); expect(Object.isFrozen(work.allowedActions)).toBe(true);
    for (const [path, init] of f.transport.mock.calls) {expect(path.startsWith(f.target.applicationBase + 'api/v1/tasks/')).toBe(true);
      expect(init.method).toBe('GET'); expect(new Headers(init.headers).has('X-CSRF-Token')).toBe(false);}
  });
  test.each(commands)(`${mode}: $action sends exactly once and recovers by protected GET`, async command => {
    const index = commands.indexOf(command), f = fixture(mode), request = {key: 'original-key', command};
    f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(receipt(index))).mockResolvedValueOnce(reply(receipt(index, true)));
    expect(await f.server.send(request, context)).toMatchObject({kind: 'receipt', action: command.action, operationId: 'op-1', revision: index === 0 ? '1' : NEXT});
    const [path, init] = f.transport.mock.calls[1]; expect(path).toBe(f.target.applicationBase + 'api/v1/tasks/' + paths[index]); expect(init.method).toBe('POST');
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('original-key'); expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('c'.repeat(64));
    expect(String(init.body)).toContain('"expected_revision":' + command.payload.expected_revision);
    if (index === 0) expect(JSON.parse(String(init.body)).title).toBe('  Clean 🧹  ');
    if (index === 2) expect(String(init.body)).toContain('"performed_at":' + REV);
    expect(await f.server.original({...request, operationId: 'op-1'}, context).result).toMatchObject({kind: 'receipt', operationId: 'op-1'});
    expect(f.transport.mock.calls[2][0]).toBe(f.target.applicationBase + 'api/v1/tasks/requests/' + command.action + '/original-key');
    expect(f.transport.mock.calls[2][1].method).toBe('GET'); expect(f.transport).toHaveBeenCalledTimes(3);
  });
}

test.each([401,403,409,422,503])('known task mutation rejection %s preserves only the safe reason', async status => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(failure(status));
  expect(await f.server.send({key: 'key', command: commands[0]}, context)).toMatchObject({kind: 'rejected', correlationId: 'cor_safe'});
  expect(f.transport).toHaveBeenCalledTimes(2);
});

test.each([[0, 'points_precision_two_required'], [2, 'invalid_input']] as const)(
  'the precision rejection requests a base correction only for creation command %s', async (index, reason) => {
    const f = fixture();
    f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)}))
      .mockResolvedValueOnce(failure(422, 'points_precision_two_required'));
    expect(await f.server.send({key: 'key', command: commands[index]}, context))
      .toEqual({kind: 'rejected', reason, correlationId: 'cor_safe'});
  });

test('the task list and detail retain a date-only deadline without inventing a time', async () => {
  const f = fixture();
  const dated = {...summary(), due_date: '2026-04-02'};
  const record = detail();
  f.transport.mockResolvedValueOnce(reply({items: [dated], next_cursor: null}))
    .mockResolvedValueOnce(reply({...record, work: {...record.work, due_date: dated.due_date}}));
  const {items} = await f.server.list(context, null).result;
  expect(items[0]).toMatchObject({dueAt: null, dueDate: '2026-04-02'});
  expect(await f.server.detail('work-1', 'home', context).result)
    .toMatchObject({dueAt: null, dueDate: '2026-04-02'});
  for (const wrong of [{...dated, due_at: 100}, {...dated, due_date: '2026-02-30'}]) {
    f.transport.mockResolvedValueOnce(reply({items: [wrong], next_cursor: null}));
    await expect(f.server.list(context, null).result).rejects.toMatchObject({code: 'invalid_response'});
  }
});
test.each(['lost', 'malformed', 'wrong_revision', 'wrong_target', 'unexpected_status'])(
  'task write with %s reply remains uncertain and never resends', async kind => {
    const f = fixture(), data = receipt(1); f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)}));
    if (kind === 'lost') f.transport.mockRejectedValueOnce(new Error('private transport detail'));
    else f.transport.mockResolvedValueOnce(reply(kind === 'malformed' ? {} : {...data, result: {...data.result,
      ...(kind === 'wrong_revision' ? {revision: '$revision'} : {}), ...(kind === 'wrong_target' ? {occurrence_id: 'other'} : {})}}, kind === 'unexpected_status' ? 201 : 200));
    expect(await f.server.send({key: 'key', command: commands[1]}, context)).toEqual({kind: 'uncertain'}); expect(f.transport).toHaveBeenCalledTimes(2);
  });
test('unsupported original or command inputs cannot become a URL or get a fresh CSRF proof', async () => {
  const f = fixture();
  expect(await f.server.send({key: '../key', command: commands[0]}, context)).toMatchObject({kind: 'rejected', reason: 'invalid_input'});
  expect(await f.server.send({key: 'key', command: {} as TaskCommand}, context)).toMatchObject({kind: 'rejected', reason: 'invalid_input'});
  await expect(f.server.original({key: '../key', command: commands[0], operationId: null}, context).result).rejects.toThrow('invalid_response');
  await expect(f.server.detail('../work', 'home', context).result).rejects.toThrow('invalid_response');
  expect(f.transport).not.toHaveBeenCalled();
});
test('original lookup binds action, key, known operation and target without disclosing an unrelated receipt', async () => {
  for (const replacement of [{action: 'task.create'}, {command_key: 'other'}, {operation_id: 'other'}, {result: {...receipt(1).result, occurrence_id: 'other'}}]) {
    const f = fixture(); f.transport.mockResolvedValueOnce(reply({...receipt(1, true), ...replacement}));
    await expect(f.server.original({key: 'original-key', command: commands[1], operationId: 'op-1'}, context).result).rejects.toThrow('invalid_response');
  }
});
test('detail rejects another household or task before publishing its content', async () => {
  for (const work of [{...detail().work, household_id: 'other'}, {...detail().work, occurrence_id: 'other'}]) {
    const f = fixture(); f.transport.mockResolvedValueOnce(reply({...detail(), work}));
    await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
  }
});

for (const mode of ['native', 'standalone'] as const) test(`${mode}: task-specific access uses its own protected contract`, async () => {
  const f = fixture(mode); f.transport.mockResolvedValueOnce(reply({household_id: 'home', member_id: 'member-1', can_create: false}));
  expect(await f.server.access(context).result).toEqual({householdId: 'home', memberId: 'member-1', canCreate: false, canReviewSchedule: false});
  f.transport.mockResolvedValueOnce(reply({household_id: 'home', member_id: 'member-1', can_create: true, can_review_schedule: true, can_configure: true}));
  expect(await f.server.access(context).result).toMatchObject({canReviewSchedule: true, canConfigure: true});
  expect(f.transport.mock.calls[0][0]).toBe(f.target.applicationBase + 'api/v1/tasks/access');
});


test('continuation tokens are encoded once and invalid limits never become URLs', async () => {
  const f = fixture(); f.transport.mockResolvedValueOnce(reply({items: [], next_cursor: null}));
  expect(await f.server.list(context, 'opaque/+?').result).toEqual({items: [], nextCursor: null});
  expect(f.transport.mock.calls[0][0]).toBe('/api/v1/tasks/occurrences?limit=25&cursor=opaque%2F%2B%3F');
  for (const value of ['', 'x'.repeat(513), 1]) await expect(f.server.list(context, value as never).result).rejects.toThrow('invalid_response');
  expect(f.transport).toHaveBeenCalledTimes(1);
});
test.each(['denied', 'malformed', 'transport'])(
  'CSRF %s cannot send a task command or disclose its raw error', async kind => {
    const f = fixture();
    if (kind === 'transport') f.transport.mockRejectedValueOnce(Error('private transport'));
    else f.transport.mockResolvedValueOnce(kind === 'denied' ? failure(403) : reply({csrf_token: 'wrong'}));
    const result = await f.server.send({key: 'key', command: commands[0]}, context);
    expect(result.kind).toBe('rejected'); expect(f.transport).toHaveBeenCalledTimes(1); expect(JSON.stringify(result)).not.toContain('private transport');
  });
test.each(['csrf', 'post'])(
  'deadline during %s fences the owned request without resending', async phase => {
    vi.useFakeTimers(); const f = fixture();
    if (phase === 'post') f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)}));
    f.transport.mockImplementation(() => new Promise<Response>(() => {}));
    const pending = f.server.send({key: 'original', command: commands[0]}, context);
    await vi.advanceTimersByTimeAsync(HTTP_TIMEOUT_MS);
    expect(await pending).toMatchObject({kind: phase === 'post' ? 'uncertain' : 'rejected'});
    expect(f.transport).toHaveBeenCalledTimes(phase === 'post' ? 2 : 1);
  });
test('a CSRF deadline at each continuation never starts a task POST with an aborted signal', async () => {
  vi.useFakeTimers({toFake: ['setTimeout', 'clearTimeout']});
  for (let delay = 0; delay < 20; delay++) {
    const f = fixture();
    f.transport.mockImplementationOnce(async () => {
      const stream = new ReadableStream<Uint8Array>({start(controller) {
        controller.enqueue(new TextEncoder().encode(JSON.stringify({csrf_token: 'c'.repeat(64)}))); controller.close();
        const later = (remaining: number) => {if (remaining === 0) vi.advanceTimersByTime(HTTP_TIMEOUT_MS); else queueMicrotask(() => later(remaining - 1));};
        queueMicrotask(() => later(delay));
      }});
      return new Response(stream, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
    });
    f.transport.mockImplementationOnce(async (_path, init) => {expect(init.signal!.aborted).toBe(false); return reply(receipt(0));});
    await f.server.send({key: 'original', command: commands[0]}, context);
    for (let index = 0; index < 20; index++) await Promise.resolve();
    expect(vi.getTimerCount()).toBe(0); expect(f.transport.mock.calls.filter(([, init]) => init.method === 'POST').length).toBeLessThanOrEqual(1);
  }
});
test('date instants, cycle identities and household-bound material lines remain exact and independent', async () => {
  const f = fixture(), data = detail();
  const binding = {household_id: 'home', reference_id: 'binding-1', product_id: 'product-1', unit_id: 'unit-1', location_id: 'shelf-1', revision: 1, precision: 6, label: 'Cleaner'};
  const modified = {...data, work: {...data.work, due_at: 0, current_cycle_id: 'cycle-1',
    definition_snapshot: {...data.work.definition_snapshot, materials: [{line_id: 'line-1', binding, planned_quantity: '3.333333'}]}}, cycle: cycle(),
    materials: [{intent_id: 'intent-1', cycle_id: 'cycle-1', line_id: 'line-1', submitted_quantity: '3.333333', quantity: '3.333333', state: 'pending_regularization',
      pending_reason: 'insufficient_stock', movement_id: null, effect_revision: 1, revision: 1, message: 'Work is saved.', action_required: 'Review stock.',
      confirmed_quantity: null, confirmed_effect_revision: null, posted_at: null}]};
  f.transport.mockResolvedValueOnce(reply(modified));
  expect(await f.server.detail('work-1', 'home', context).result).toMatchObject({dueAt: '0', currentCycleId: 'cycle-1', pendingMaterials: true,
    cycle: {cycleId: 'cycle-1', performedAt: REV}, materials: [{lineId: 'line-1', label: 'Cleaner', plannedQuantity: '3.333333'}]});
  f.transport.mockResolvedValueOnce(reply({...modified, materials: [{...modified.materials[0], state: 'not_used'}]}));
  expect((await f.server.detail('work-1', 'home', context).result).pendingMaterials).toBe(false);
  for (const bad of [{...modified, cycle: {...cycle(), household_id: 'other'}},
    {...modified, work: {...modified.work, current_cycle_id: 'other'}},
    {...modified, work: {...modified.work, definition_snapshot: {...modified.work.definition_snapshot, materials: [{line_id: 'line-1', binding, planned_quantity: '1.0'}]}}}]) {
    f.transport.mockResolvedValueOnce(reply(bad)); await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
  }
});
test('malformed or duplicate list facts do not become partial task content', async () => {
  const f = fixture();
  for (const data of [{items: [{...summary(), title: ''}], next_cursor: null}, {items: [summary(), summary()], next_cursor: null},
    {items: [{...summary(), due_at: '$revision', current_cycle_id: 'cycle-1'}], next_cursor: null}]) {
    f.transport.mockResolvedValueOnce(reply(data));
    if (data.items[0].title === '' || data.items.length === 2) await expect(f.server.list(context, null).result).rejects.toThrow('invalid_response');
    else expect((await f.server.list(context, null).result).items[0].dueAt).toBe(REV);
  }
});
test('historical originals remain absent effects and cannot claim pending or current delivery', async () => {
  const f = fixture(), request = {key: 'original-key', command: commands[0], operationId: null};
  f.transport.mockResolvedValueOnce(reply({...receipt(0, true), state: 'historical', archived_by: 'restore-1', delivery: 'suppressed'}));
  expect(await f.server.original(request, context).result).toMatchObject({stage: 'historical', archivedBy: 'restore-1'});
  for (const patch of [{state: 'historical', archived_by: null, delivery: 'suppressed'}, {state: 'historical', archived_by: 'restore-1', delivery: 'pending'}, {delivery: 'suppressed'}]) {
    f.transport.mockResolvedValueOnce(reply({...receipt(0, true), ...patch})); await expect(f.server.original(request, context).result).rejects.toThrow('invalid_response');
  }
});


test('material unit precision comes from the server and incompatible planned amounts fail closed', async () => {
  const f = fixture(), data = detail(), binding = {household_id: 'home', reference_id: 'ref', product_id: 'product', unit_id: 'unit', location_id: 'shelf', revision: 1, precision: 0, label: 'Cloth'};
  for (const [planned_quantity, precision, valid] of [['2', 0, true], ['0.5', 0, false], ['1', 7, false]] as const) {
    f.transport.mockResolvedValueOnce(reply({...data, work: {...data.work, definition_snapshot: {...data.work.definition_snapshot,
      materials: [{line_id: 'line-1', binding: {...binding, precision}, planned_quantity}]}}}));
    if (valid) expect((await f.server.detail('work-1', 'home', context).result).materials[0]).toMatchObject({precision: 0, plannedQuantity: '2'});
    else await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
  }
});

test('category catalog and historical task snapshots are verified against the current household', async () => {
  const f = fixture();
  const category = {category_id: 'garden', household_id: 'home', label: 'Café <b>', revision: '$revision', archived: false};
  const base = {household_id: 'home', member_id: 'member-1', can_create: true};
  f.transport.mockResolvedValueOnce(reply({...base, category_catalog: {categories: [category], can_manage: true}}));
  expect((await f.server.access(context).result).categoryCatalog).toEqual({
    categories: [{id: 'garden', label: 'Café <b>', revision: REV}], canManage: true,
  });
  for (const categories of [null, [category, category], [{...category, household_id: 'foreign'}],
    [{...category, archived: true}], [{...category, label: ' Cafe\u0301 '}], Array(101).fill(category)]) {
    f.transport.mockResolvedValueOnce(reply({...base, category_catalog: {categories, can_manage: true}}));
    await expect(f.server.access(context).result).rejects.toThrow('invalid_response');
  }
  const raw = detail(), snapshot = raw.work.definition_snapshot;
  f.transport.mockResolvedValueOnce(reply({...raw, work: {...raw.work,
    definition_snapshot: {...snapshot, category_label: category.label, content: {...snapshot.content, category_id: 'garden'}}}}));
  expect((await f.server.detail('work-1', 'home', context).result).categoryLabel).toBe(category.label);
  f.transport.mockResolvedValueOnce(reply({...raw, work: {...raw.work, definition_snapshot: {...snapshot, category_label: category.label}}}));
  await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
});

test('category commands preserve exact revision, original label and action during lost reply recovery', async () => {
  for (const kind of ['create', 'rename', 'archive'] as const) {
    const action = 'task.category.' + kind, archive = kind === 'archive';
    const command = taskCommand({action, ...kind === 'create' ? {} : {categoryId: 'garden'}, payload: {
      expected_revision: kind === 'create' ? 0 : REV, ...archive ? {} : {label: '  Cafe\u0301 <b>  '},
    }})!;
    const f = fixture(), original = {key: 'category-key', command};
    const category = {category_id: 'garden', household_id: 'home', label: 'Café <b>', revision: kind === 'create' ? 1 : '$next', archived: archive};
    const committed = {...receipt(0), result: category};
    f.transport.mockResolvedValueOnce(reply({csrf_token: 'c'.repeat(64)})).mockResolvedValueOnce(reply(committed));
    expect(await f.server.send(original, context)).toMatchObject({action, occurrenceId: null, state: archive ? 'archived' : 'active'});
    const [url, init] = f.transport.mock.calls[1];
    expect(url).toBe('/api/v1/tasks/categories' + (kind === 'create' ? '' : archive ? '/garden/archive' : '/garden'));
    expect(init.method).toBe(kind === 'rename' ? 'PUT' : 'POST');
    expect(String(init.body)).toContain('"expected_revision":' + (kind === 'create' ? 0 : REV));
    if (!archive) expect(JSON.parse(String(init.body)).label).toBe('  Cafe\u0301 <b>  ');
    f.transport.mockResolvedValueOnce(reply({...committed, state: 'historical', archived_by: 'restored', action, command_key: original.key}));
    expect(await f.server.original({...original, operationId: 'op-1'}, context).result).toMatchObject({stage: 'historical', archivedBy: 'restored'});
    expect(f.transport.mock.calls[2][0]).toBe('/api/v1/tasks/categories/requests/' + action + '/category-key');
    f.transport.mockResolvedValueOnce(reply({...committed, action, command_key: 'different-key'}));
    await expect(f.server.original({...original, operationId: null}, context).result).rejects.toThrow('invalid_response');
  }
});

test('task detail decodes the current completion allocation affordance before settings are read', async () => {
  const f = fixture();
  for (const completion_points of ['manual', 'manager_required'] as const) {
    f.transport.mockResolvedValueOnce(reply({...detail(), completion_points}));
    expect(await f.server.detail('work-1', 'home', context).result).toMatchObject({completionPoints: completion_points});
  }
  f.transport.mockResolvedValueOnce(reply({...detail(), completion_points: 'other'}));
  await expect(f.server.detail('work-1', 'home', context).result).rejects.toThrow('invalid_response');
});

const emptyOverviewGroup = {total: 0, items: []};
const emptyOverview = {assigned: emptyOverviewGroup, unclaimed: emptyOverviewGroup,
  due_today: emptyOverviewGroup, overdue: emptyOverviewGroup, upcoming_maintenance: emptyOverviewGroup};
const dueWireItem = {occurrence_id: 'due', title: 'Check meter', state: 'available',
  deadline: {local_date: null, instant_ms: '1775113200000', time_zone: 'Europe/Madrid'}};
const overdueWireItem = {occurrence_id: 'late', title: 'Change filter', state: 'blocked',
  deadline: {local_date: '2026-04-01', instant_ms: null, time_zone: 'Europe/Madrid'}};
const maintenanceWireItem = {occurrence_id: 'maintenance', title: 'Drain the tank', state: 'assigned',
  deadline: {local_date: '2026-04-05', instant_ms: null, time_zone: 'Europe/Madrid'}};

test('Overview reads exact counts, bounded task rows and both effective deadline precisions', async () => {
  const f = fixture('native');
  const items = Array.from({length: 25}, (_, index) => ({occurrence_id: 'work-' + index,
    title: 'Clean <b>table</b>', state: 'assigned'}));
  f.transport.mockResolvedValueOnce(reply({...emptyOverview, assigned: {total: 37, items},
    due_today: {total: 1, items: [dueWireItem]}, overdue: {total: 1, items: [overdueWireItem]},
    upcoming_maintenance: {total: 1, items: [maintenanceWireItem]}}));
  const result = await f.server.overview(context).result;
  expect(result.assigned.total).toBe(37);
  expect(result.assigned.items).toHaveLength(25);
  expect(result.assigned.items[0]).toEqual({id: 'work-0', title: 'Clean <b>table</b>', state: 'assigned'});
  expect(result.dueToday.items[0].deadline).toEqual({day: null, instant: 1775113200000, zone: 'Europe/Madrid'});
  expect(result.overdue.items[0].deadline).toEqual({day: '2026-04-01', instant: null, zone: 'Europe/Madrid'});
  expect(result.upcomingMaintenance.items[0].deadline).toEqual({day: '2026-04-05', instant: null, zone: 'Europe/Madrid'});
  const [path, init] = f.transport.mock.calls[0];
  expect(path).toBe(f.target.applicationBase + 'api/v1/tasks/overview');
  expect(init.method).toBe('GET');
  expect(new Headers(init.headers).has('X-Domus-Context')).toBe(true);
});

test.each([
  {total: 1, items: null},
  {total: 1, items: []},
  {total: 1, items: [{occurrence_id: 'work', title: 'Clean', state: 'completed'}]},
  {total: 2, items: Array.from({length: 2}, () => ({occurrence_id: 'same', title: 'Clean', state: 'assigned'}))},
])('Overview rejects an incomplete or inconsistent group', async assigned => {
  const f = fixture();
  f.transport.mockResolvedValueOnce(reply({...emptyOverview, assigned}));
  await expect(f.server.overview(context).result).rejects.toMatchObject({code: 'invalid_response'});
});

test('Overview rejects malformed, ambiguous and duplicate deadline rows', async () => {
  const f = fixture();
  const group = (item: object) => ({total: 1, items: [item]});
  for (const deadline of [
    {...dueWireItem.deadline, instant_ms: '253402300800000'},
    {...dueWireItem.deadline, instant_ms: null},
    {...dueWireItem.deadline, local_date: '2026-02-30'},
    {...dueWireItem.deadline, local_date: '2026-04-01'},
    {...dueWireItem.deadline, time_zone: 'Invalid/Zone'},
  ]) {
    f.transport.mockResolvedValueOnce(reply({...emptyOverview, due_today: group({...dueWireItem, deadline})}));
    await expect(f.server.overview(context).result).rejects.toMatchObject({code: 'invalid_response'});
  }
  f.transport.mockResolvedValueOnce(reply({...emptyOverview, due_today: group(dueWireItem), overdue: group(dueWireItem)}));
  await expect(f.server.overview(context).result).rejects.toMatchObject({code: 'invalid_response'});
  f.transport.mockResolvedValueOnce(reply({...emptyOverview, overdue: group(overdueWireItem),
    upcoming_maintenance: group(overdueWireItem)}));
  await expect(f.server.overview(context).result).rejects.toMatchObject({code: 'invalid_response'});
  f.transport.mockResolvedValueOnce(reply({...emptyOverview, upcoming_maintenance: {total: 1, items: []}}));
  await expect(f.server.overview(context).result).rejects.toMatchObject({code: 'invalid_response'});
});

function materialHistoryWire() {
  return {occurrence_id:'work-1',cycle:{...cycle(),closed_at:'$revision'},materials:[materialReceipt().result.material],allowed_actions:['materials.settle']};
}
function historyWork() {
  return {occurrenceId:'work-1',definitionId:'definition-1',definitionRevision:revisionValue('1'),title:'QA Soap',description:'',priority:'normal' as const,
    state:'available' as const,revision:revisionValue('3'),assigneeIds:[],dueAt:null,currentCycleId:null,cycle:null,allowedActions:[],
    materials:[{lineId:'line-1',label:'Soap',plannedQuantity:'2',precision:0,unitId:'piece',locationId:'pantry'}],
    materialRecording:'review_on_completion' as const,dependencyReviewRequired:false,pendingMaterials:false};
}
test.each(['native','standalone'] as const)('%s historical usage preserves its original cycle and requests one bounded page', async mode => {
  const f=fixture(mode), work=historyWork(), wire=materialHistoryWire();
  for (const cursor of [null,'opaque-cursor']) {
    f.transport.mockResolvedValueOnce(reply({items:[wire],next_cursor:cursor}));
    const result=await f.server.materialHistory(work,'home',cursor,context).result;
    expect(result).toMatchObject({items:[{cycle:{cycleId:'cycle-1'},closedAt:REV,materialOutcomes:[{intentId:'intent-1',lineId:'line-1'}]}],nextCursor:cursor});
    expect(f.transport.mock.calls.at(-1)![0]).toBe(f.target.applicationBase+'api/v1/tasks/occurrences/work-1/material-history?limit=1'+(cursor?'&cursor='+cursor:''));
  }
  f.transport.mockResolvedValueOnce(reply(wire));
  expect((await f.server.materialCycle(work,'home','cycle-1',context).result).allowedActions).toEqual(['materials.settle']);
  expect(f.transport.mock.calls.at(-1)![0]).toBe(f.target.applicationBase+'api/v1/tasks/occurrences/work-1/materials?cycle_id=cycle-1');
  f.transport.mockResolvedValueOnce(reply({items:[],next_cursor:null}));
  expect((await f.server.materialHistory(work,'home',null,context).result).items).toEqual([]);
  expect(f.transport.mock.calls.every(call=>call[1].method==='GET')).toBe(true);
  await expect(f.server.materialHistory(work,'home','',context).result).rejects.toThrow('invalid_response');
  await expect(f.server.materialHistory(work,'home','x'.repeat(513),context).result).rejects.toThrow('invalid_response');
});
test.each(['work','home','cycle','open','line','duplicate_intent','duplicate_line','action','count','cursor','closed_time'] as const)(
  'historical material %s substitution cannot enter a current task projection', async kind => {
    const f=fixture(), wire=materialHistoryWire();
    const raw:Record<string,any>={items:[wire],next_cursor:null};
    if(kind==='work')wire.occurrence_id='foreign';
    if(kind==='home')wire.cycle.household_id='foreign';
    if(kind==='cycle')wire.materials[0].cycle_id='foreign';
    if(kind==='open')wire.cycle.closed_at=null as unknown as string;
    if(kind==='line')wire.materials[0].line_id='foreign';
    if(kind==='duplicate_intent')wire.materials.push({...wire.materials[0]});
    if(kind==='duplicate_line')wire.materials.push({...wire.materials[0],intent_id:'other'});
    if(kind==='action')wire.allowed_actions=['complete'];
    if(kind==='count')raw.items.push({...wire});
    if(kind==='cursor')raw.next_cursor='';
    if(kind==='closed_time')wire.cycle.closed_at='invalid';
    f.transport.mockResolvedValueOnce(reply(raw));
    await expect(f.server.materialHistory(historyWork(),'home',null,context).result).rejects.toThrow('invalid_response');
  });
test('direct material cycle lookup rejects another valid cycle even when its outcomes agree', async () => {
  const f=fixture(), wire=materialHistoryWire();
  f.transport.mockResolvedValueOnce(reply(wire));
  await expect(f.server.materialCycle(historyWork(),'home','other-cycle',context).result).rejects.toThrow('invalid_response');
});
