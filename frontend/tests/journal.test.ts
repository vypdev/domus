import {expect, test} from 'vitest';
import {appendRequest, emptyJournal, inspectJournal, recordOutcome, discardRequest,
  JournalError, JOURNAL_LIFETIME} from '../src/domain/journal';
import type {Journal, JournalContext, RequestStage} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const enroll = {action: 'enroll' as const, payload: {expected_revision: 0 as const}};
const setup = {action: 'setup' as const, payload: {name: '  My household  ', time_zone: 'UTC',
  expected_revision: 0 as const, mapping_mode: 'all_ha_administrators' as const}};
const started = () => appendRequest(emptyJournal(context, 1000), 'request-1', enroll, 1000);
const raw = () => JSON.parse(JSON.stringify(started()));
const fault = (run: () => unknown, code: string) => {
  expect(run).toThrow(JournalError); expect(run).toThrow(code);
};

test('C05/C07: both commands retain original values and produce deep immutable copies', () => {
  const value = appendRequest(started(), 'request-2', setup, 1100);
  expect(value.records[1]).toEqual({key: 'request-2', ...setup, createdAt: 1100,
    expiresAt: 1100 + JOURNAL_LIFETIME, stage: 'prepared', operationId: null});
  for (const item of [value, value.context, value.records, value.records[1], value.records[1]!.payload])
    expect(Object.isFrozen(item)).toBe(true);
  const input = raw(); const result = inspectJournal(input, context, 1200).journal;
  input.records[0].payload.expected_revision = 88; input.context.subject = 'different';
  expect(result.records[0]!.payload.expected_revision).toBe(0);
  expect(result.context.subject).toBe(context.subject);
});

test.each([null, [], 'text', {}, {version: 2}, {...raw(), extra: 'cookie'},
  {...raw(), version: true}, {...raw(), records: {}}, {...raw(), records: Array(9).fill(raw().records[0])}])(
  'C05: rejects malformed or future envelope %j', value => fault(() => inspectJournal(value, context, 1000), 'invalid_journal'),
);

test.each([
  {installationId: 'wrong'}, {installationId: context.installationId.toUpperCase()},
  {channel: 'nightly'}, {subject: ''}, {subject: 'wrong/subject'}, {subject: 'x'.repeat(129)},
  {subject: 7}, {extra: 'token'},
])('rejects malformed scope %j', change => {
  const value = raw(); value.context = {...value.context, ...change};
  fault(() => inspectJournal(value, context, 1000), 'invalid_journal');
});

test.each([null, 4, [], {}, {key: ''}, {key: '-bad'}, {key: 'x'.repeat(129)},
  {action: 'delete'}, {payload: {}}, {payload: {expected_revision: 1}},
  {payload: {expected_revision: false}}, {payload: {expected_revision: 0, csrf_token: 'secret'}},
  {stage: 'future'}, {stage: 'prepared', operationId: 'operation'},
  {stage: 'committed'}, {stage: 'historical', operationId: 'bad/id'}, {extra: 'credential'}])(
  'C05: rejects malformed record %j', change => {
    const value = raw(); value.records[0] = change === null || typeof change !== 'object'
      || Array.isArray(change) || Object.keys(change).length === 0 ? change : {...value.records[0], ...change};
    fault(() => inspectJournal(value, context, 1000), 'invalid_journal');
  },
);

test.each([{name: ''}, {time_zone: ''}, {expected_revision: 1}, {mapping_mode: 'selected_ha_user'},
  {selected_ha_user_id: 'other'}, {name: '\uD800'}, {name: 'Home\u007F'},
  {time_zone: 'UTC\u0085'}])('rejects unsupported setup payload %j', change => {
  const value = raw(); value.records[0] = {...value.records[0], ...setup,
    payload: {...setup.payload, ...change}};
  fault(() => inspectJournal(value, context, 1000), 'invalid_journal');
});

test.each([NaN, Infinity, -1, 0.5, Number.MAX_SAFE_INTEGER + 1])('C06: rejects invalid time %s', time => {
  fault(() => emptyJournal(context, time), 'invalid_journal_time');
  const value = raw(); value.observedAt = time;
  fault(() => inspectJournal(value, context, 1000), 'invalid_journal_time');
});

test('C06: backward/future clocks and changed deadlines fail without extending retention', () => {
  fault(() => inspectJournal(started(), context, 999), 'invalid_journal_time');
  for (const change of [{createdAt: 1001}, {createdAt: -1}, {expiresAt: 3601001},
    {expiresAt: NaN}, {createdAt: Number.MAX_SAFE_INTEGER}]) {
    const value = raw(); Object.assign(value.records[0], change);
    expect(() => inspectJournal(value, context, 1000)).toThrow(JournalError);
  }
  const later = inspectJournal(started(), context, 2000).journal;
  expect(later.observedAt).toBe(2000); expect(later.records[0]!.expiresAt).toBe(3601000);
  expect(inspectJournal(later, context, 3600999).journal.records).toHaveLength(1);
  expect(inspectJournal(later, context, 3601000).journal.records).toEqual([]);
});

test('C25: eight records fit, a ninth and a duplicate key do not evict prior work', () => {
  let journal = emptyJournal(context, 1000);
  for (let index = 0; index < 8; index++) journal = appendRequest(journal, `key${index}`, enroll, 1000);
  expect(journal.records).toHaveLength(8);
  fault(() => appendRequest(journal, 'ninth', enroll, 1000), 'journal_capacity');
  fault(() => appendRequest(started(), 'request-1', setup, 1000), 'duplicate_request');
  const duplicate = raw(); duplicate.records.push(duplicate.records[0]);
  fault(() => inspectJournal(duplicate, context, 1000), 'duplicate_request');
  expect(appendRequest(journal, 'after-expiry', enroll, 3601000).records).toHaveLength(1);
});

test.each(['uncertain', 'rejected', 'committed', 'historical'] as const)(
  'C07: %s retains original payload/key/deadline', stage => {
    const operationId = stage === 'committed' || stage === 'historical' ? 'op-1' : null;
    const journal = recordOutcome(started(), 'request-1', {stage, operationId}, 2000);
    expect(journal.records[0]).toEqual({...started().records[0], stage, operationId});
    expect(inspectJournal(journal, context, 2001).journal.records[0]!.stage).toBe(stage);
  },
);

test('known receipts cannot change identity or lose their known outcome', () => {
  const committed = recordOutcome(started(), 'request-1', {stage: 'committed', operationId: 'op-1'}, 1000);
  expect(recordOutcome(committed, 'request-1', {stage: 'historical', operationId: 'op-1'}, 1100)
    .records[0]!.stage).toBe('historical');
  for (const outcome of [{stage: 'committed' as const, operationId: 'op-2'},
    {stage: 'uncertain' as const, operationId: null}])
    fault(() => recordOutcome(committed, 'request-1', outcome, 1100), 'original_operation_changed');
  fault(() => recordOutcome(started(), 'missing', {stage: 'rejected', operationId: null}, 1000), 'request_not_found');
  expect(() => recordOutcome(started(), 'request-1', {stage: 'prepared' as never, operationId: null}, 1000))
    .toThrow(JournalError);
});

test('updating and dismissing one request preserves its neighbouring original record', () => {
  const two = appendRequest(started(), 'request-2', setup, 1000);
  const result = recordOutcome(two, 'request-2', {stage: 'committed', operationId: 'op-2'}, 1100);
  expect(result.records[0]).toEqual(two.records[0]);
  expect(discardRequest(result, 'request-2', 1200).records).toEqual([two.records[0]]);
  fault(() => appendRequest(emptyJournal(context, Number.MAX_SAFE_INTEGER), 'overflow', enroll,
    Number.MAX_SAFE_INTEGER), 'invalid_journal_time');
});

test.each(['1000', null, true])('non-numeric timestamps %j are never coerced', value => {
  const item = raw(); item.observedAt = value;
  fault(() => inspectJournal(item, context, 1000), 'invalid_journal_time');
});

test('same-sized wrong fields cannot replace required fields', () => {
  const item = raw(); delete item.version; item.authorization = 'secret';
  fault(() => inspectJournal(item, context, 1000), 'invalid_journal');
});

test.each(['prepared', 'uncertain', 'committed', 'historical', 'rejected'] as RequestStage[])(
  'explicit dismissal respects unresolved %s records', stage => {
    let value: Journal = started();
    if (stage !== 'prepared') value = recordOutcome(value, 'request-1', {stage,
      operationId: stage === 'committed' || stage === 'historical' ? 'op-1' : null}, 1000);
    if (stage === 'prepared' || stage === 'uncertain') fault(() => discardRequest(value, 'request-1', 1000), 'unresolved_request');
    else expect(discardRequest(value, 'request-1', 1000).records).toEqual([]);
  },
);

test('unknown discard target is not silently ignored', () => {
  fault(() => discardRequest(started(), 'other', 1000), 'request_not_found');
});

test.each([{subject: 'other'}, {channel: 'stable' as const},
  {installationId: '11111111-1111-1111-1111-111111111111'}])('C41: different %j reveals no old record', change => {
    const value = raw(); Object.defineProperty(value, 'records', {enumerable: true,
      get() {throw new Error('old payload must not be read');}});
    const result = inspectJournal(value, {...context, ...change}, 1000);
    expect(result.kind).toBe('context_changed'); expect(result.journal.records).toEqual([]);
  },
);
