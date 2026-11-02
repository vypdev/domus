import {expect, test} from 'vitest';
import {administrationCommand} from '../src/domain/administration-commands';
import {emptyAdministrationJournal, inspectAdministrationJournal, administrationView,
  prepareAdministration, recordAdministration, forgetAdministration} from '../src/domain/administration-journal';
import {JournalError, JOURNAL_LIFETIME} from '../src/domain/journal';
import type {JournalContext} from '../src/domain/journal';
import {administrationCommandBody, administrationJSON, responseRevision} from '../src/adapters/administration-json';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const other = {...context, subject: 'b'.repeat(32)};
const revision = '9007199254740993';
const examples = [
  {action: 'household.update', payload: {expected_revision: revision, name: '  Home  ', time_zone: 'UTC'}},
  {action: 'member.update', memberId: 'member-1', payload: {expected_revision: revision,
    role: 'restricted', status: 'active', exceptions: [{permission: 'tasks.complete', allow: true}]}},
  {action: 'policy.update', payload: {expected_revision: revision, mapping_mode: 'selected_ha_user',
    target_ha_user_id: 'b'.repeat(32), adjustments: [{role: 'adult', permission: 'inventory.manage', allow: false}]}},
  {action: 'member.presentation.update', memberId: 'member-1', payload: {expected_revision: revision, alias: '  <b>Literal</b>  '}},
  {action: 'member.preferences.update', payload: {expected_revision: revision, locale: 'es', routine_participation_summaries: false}},
];
const preferences = () => administrationCommand(examples[4]);
const started = () => prepareAdministration(emptyAdministrationJournal(1000), context, 'key', preferences(), 1000);
const raw = () => JSON.parse(JSON.stringify(started()));

test.each(examples)('closed command retains the original values for $action', example => {
  const command = administrationCommand(example);
  expect(command).toEqual(example);
  expect(Object.isFrozen(command)).toBe(true);
  expect(Object.isFrozen(command.payload)).toBe(true);
  expect(command.payload.expected_revision).toBe(revision);
});

test.each(examples)('wire encoder preserves the exact journal intent for $action', example => {
  const command = administrationCommand(example);
  const body = administrationCommandBody(command);
  const decoded = administrationJSON(body) as Record<string, unknown>;
  expect(responseRevision(decoded.expected_revision)).toBe(revision);
  const {expected_revision: _revision, ...values} = decoded;
  const {expected_revision: _original, ...original} = example.payload;
  expect(values).toEqual(original);
  expect(Object.hasOwn(decoded, 'memberId')).toBe(false);
  expect(Object.hasOwn(decoded, 'action')).toBe(false);
});

test('command copies nested decisions and never normalizes the submitted intent', () => {
  const input = structuredClone(examples[1]);
  const command = administrationCommand(input);
  (input.payload as {exceptions: {allow: boolean}[]}).exceptions[0].allow = false;
  expect(command).toEqual(examples[1]);
  if (command.action !== 'member.update') throw new Error('Expected the original member command');
  expect(Object.isFrozen(command.payload.exceptions)).toBe(true);
  expect(administrationCommand(examples[0]).payload).toHaveProperty('name', '  Home  ');
  expect(administrationCommand(examples[3]).payload).toHaveProperty('alias', '  <b>Literal</b>  ');
});

test.each([null, [], 1, {}, {action: 'setup', payload: {}}, {action: 'enroll', payload: {}},
  {...examples[4], memberId: 'other'}, {...examples[4], csrf: 'secret'},
  {...examples[4], payload: {...examples[4].payload, ha_user_id: 'a'.repeat(32)}},
  {...examples[4], payload: {...examples[4].payload, expected_revision: 1}},
  {...examples[4], payload: {...examples[4].payload, expected_revision: '01'}},
  {...examples[4], payload: {...examples[4].payload, locale: 'future'}},
  {...examples[4], payload: {...examples[4].payload, routine_participation_summaries: 'true'}},
  {...examples[3], memberId: 'invalid/id'}, {...examples[3], payload: {expected_revision: '1', alias: '\nName'}},
  {...examples[0], payload: {expected_revision: '1', name: ' ', time_zone: 'UTC'}},
  {...examples[0], payload: {expected_revision: '1', name: 'Home', time_zone: ''}},
  {...examples[0], payload: {expected_revision: '1', name: 'x'.repeat(161), time_zone: 'UTC'}},
  {...examples[0], payload: {expected_revision: '1', name: '\ud800', time_zone: 'UTC'}},
  {...examples[1], payload: {...examples[1].payload, role: 'future'}},
  {...examples[1], payload: {...examples[1].payload, status: 'future'}},
  {...examples[1], payload: {...examples[1].payload, exceptions: 'wrong'}},
  {...examples[1], payload: {...examples[1].payload, exceptions: Array(257).fill({permission: 'tasks.read', allow: true})}},
  {...examples[1], payload: {...examples[1].payload, exceptions: [{permission: 'tasks.configure', allow: true}]}},
  {...examples[1], payload: {...examples[1].payload, exceptions: [{permission: 'future.read', allow: true}]}},
  {...examples[1], payload: {...examples[1].payload, exceptions: [{permission: 'tasks.read', allow: 1}]}},
  {...examples[1], payload: {...examples[1].payload, exceptions: Array(2).fill({permission: 'tasks.read', allow: true})}},
  {...examples[2], payload: {...examples[2].payload, adjustments: Array(2).fill({role: 'adult', permission: 'tasks.read', allow: true})}},
  {...examples[2], payload: {...examples[2].payload, adjustments: [{role: 'future', permission: 'tasks.read', allow: true}]}},
  {...examples[2], payload: {...examples[2].payload, mapping_mode: 'future'}},
  {...examples[2], payload: {...examples[2].payload, mapping_mode: 'all_ha_administrators'}},
  {...examples[2], payload: {...examples[2].payload, target_ha_user_id: null}},
  {...examples[2], payload: {...examples[2].payload, target_ha_user_id: 'not-a-ha-id'}},
])('unsupported command case %# cannot enter recovery', value => {
  expect(() => administrationCommand(value)).toThrow('invalid_command');
});

test('all mapping modes, nullable alias and browser-following locale retain their exact types', () => {
  for (const mapping_mode of ['all_ha_administrators', 'setup_administrator']) {
    const value = {...examples[2], payload: {...examples[2].payload, mapping_mode,
      target_ha_user_id: mapping_mode === 'all_ha_administrators' ? null : 'b'.repeat(32)}};
    expect(administrationCommand(value)).toEqual(value);
  }
  expect(administrationCommand({...examples[3], payload: {expected_revision: '1', alias: null}}).payload).toHaveProperty('alias', null);
  expect(administrationCommand({...examples[4], payload: {expected_revision: '1', locale: null, routine_participation_summaries: true}}).payload).toHaveProperty('locale', null);
});

test('household name validation follows backend Unicode whitespace while retaining the original text', () => {
  const value = (name: string) => ({...examples[0], payload: {expected_revision: '1', name, time_zone: 'UTC'}});
  expect(() => administrationCommand(value('\u0085'))).toThrow('invalid_command');
  expect(administrationCommand(value('\uFEFF'))).toEqual(value('\uFEFF'));
  expect(administrationCommand(value('\u0085Home\u0085'))).toEqual(value('\u0085Home\u0085'));
});

test('separate namespace, immutable context, original high revision and one-hour deadline survive inspection', () => {
  const original = started();
  const decoded = inspectAdministrationJournal(JSON.parse(JSON.stringify(original)), 1100);
  expect(decoded.namespace).toBe('administration');
  expect(decoded.version).toBe(1);
  expect(decoded.records[0]).toMatchObject({context, key: 'key', ...examples[4],
    createdAt: 1000, expiresAt: 1000 + JOURNAL_LIFETIME, stage: 'prepared', operationId: null});
  for (const value of [decoded, decoded.records, decoded.records[0], decoded.records[0].context, decoded.records[0].payload])
    expect(Object.isFrozen(value)).toBe(true);
  expect(inspectAdministrationJournal(decoded, 3601000).records).toEqual([]);
});

test('all five original actions retain their supported target and independent payload through persistence', () => {
  let journal = emptyAdministrationJournal(1000);
  for (const [index, example] of examples.entries())
    journal = prepareAdministration(journal, context, 'key' + index, administrationCommand(example), 1000);
  const decoded = inspectAdministrationJournal(JSON.parse(JSON.stringify(journal)), 1100);
  expect(decoded.records.map(record => ({action: record.action, payload: record.payload,
    ...('memberId' in record ? {memberId: record.memberId} : {})}))).toEqual(examples);
});

test('another subject, installation or channel cannot view, update or forget the original', () => {
  for (const changed of [other, {...context, channel: 'stable' as const},
    {...context, installationId: '11111111-1111-1111-1111-111111111111'}]) {
    expect(administrationView(started(), changed, 1000).records).toEqual([]);
    expect(() => recordAdministration(started(), changed, 'key', {stage: 'committed', operationId: 'op'}, 1000)).toThrow('request_not_found');
    expect(() => forgetAdministration(started(), changed, 'key', 1000)).toThrow('request_not_found');
  }
});

test('switching contexts retains eligible originals while the eight-record budget covers the entire namespace', () => {
  let journal = prepareAdministration(started(), other, 'key', preferences(), 1000);
  expect(administrationView(journal, context, 1100).records).toHaveLength(1);
  expect(administrationView(journal, other, 1100).records).toHaveLength(1);
  for (let index = 2; index < 8; index++) journal = prepareAdministration(journal, other, 'key' + index, preferences(), 1100);
  expect(() => prepareAdministration(journal, context, 'ninth', preferences(), 1100)).toThrow('journal_capacity');
  expect(() => prepareAdministration(started(), context, 'key', preferences(), 1100)).toThrow('duplicate_request');
  expect(prepareAdministration(journal, context, 'after-expiry', preferences(), 3601100).records).toHaveLength(1);
});

test.each(['uncertain', 'rejected', 'committed', 'historical'] as const)('original %s outcome never changes intent or retention', stage => {
  const operationId = stage === 'committed' || stage === 'historical' ? 'op' : null;
  const current = recordAdministration(started(), context, 'key', {stage, operationId}, 1100);
  expect(current.records[0]).toEqual({...started().records[0], stage, operationId});
  if (stage === 'uncertain') expect(() => forgetAdministration(current, context, 'key', 1200)).toThrow('unresolved_request');
  else expect(forgetAdministration(current, context, 'key', 1200).records).toEqual([]);
});

test('known operation cannot change or be forgotten as an uncertain request; other contexts survive dismissal', () => {
  const initial = prepareAdministration(started(), other, 'key', preferences(), 1000);
  const saved = recordAdministration(initial, context, 'key', {stage: 'committed', operationId: 'op'}, 1000);
  const historical = recordAdministration(saved, context, 'key', {stage: 'historical', operationId: 'op'}, 1100);
  expect(historical.records[1]).toEqual(initial.records[1]);
  for (const outcome of [{stage: 'committed', operationId: 'replacement'}, {stage: 'uncertain', operationId: null}])
    expect(() => recordAdministration(saved, context, 'key', outcome as never, 1100)).toThrow('original_operation_changed');
  expect(forgetAdministration(historical, context, 'key', 1200).records).toEqual([initial.records[1]]);
  expect(() => forgetAdministration(started(), context, 'key', 1100)).toThrow('unresolved_request');
});

test.each([null, [], {}, {...raw(), namespace: 'entry'}, {...raw(), version: 2},
  {...raw(), token: 'secret'}, {...raw(), records: {}}, {...raw(), records: Array(9).fill(raw().records[0])}])(
  'forged envelope case %# fails closed', value => expect(() => inspectAdministrationJournal(value, 1100)).toThrow(JournalError));

test.each([{key: ''}, {stage: 'future'}, {stage: 'prepared', operationId: 'op'},
  {stage: 'committed'}, {stage: 'committed', operationId: 'invalid/id'},
  {payload: {}}, {cookie: 'secret'}, {createdAt: 1001}, {expiresAt: 3601001},
  {context: {...context, subject: 'invalid'}}, {context: {...context, channel: 'nightly'}},
  {context: {...context, installationId: 'wrong'}}, {context: {...context, token: 'secret'}}])(
  'forged record case %# fails closed', change => {
    const value = raw(); Object.assign(value.records[0], change);
    expect(() => inspectAdministrationJournal(value, 1100)).toThrow(JournalError);
  });

test.each([NaN, Infinity, -1, .5, Number.MAX_SAFE_INTEGER + 1, '1000', null])('clock case %# never extends retention', value => {
  expect(() => emptyAdministrationJournal(value as never)).toThrow('invalid_journal_time');
});

test('backward time, overflow, duplicates and invalid outcomes preserve the original journal', () => {
  expect(() => inspectAdministrationJournal(started(), 999)).toThrow('invalid_journal_time');
  expect(() => prepareAdministration(emptyAdministrationJournal(Number.MAX_SAFE_INTEGER), context, 'key', preferences(), Number.MAX_SAFE_INTEGER)).toThrow('invalid_journal_time');
  const duplicate = raw(); duplicate.records.push(duplicate.records[0]);
  expect(() => inspectAdministrationJournal(duplicate, 1100)).toThrow('duplicate_request');
  for (const outcome of [{stage: 'prepared', operationId: null}, {stage: 'future', operationId: null},
    {stage: 'rejected', operationId: 'op'}, {stage: 'committed', operationId: null},
    {stage: 'committed', operationId: 'op', csrf: 'secret'}])
    expect(() => recordAdministration(started(), context, 'key', outcome as never, 1100)).toThrow(JournalError);
});
