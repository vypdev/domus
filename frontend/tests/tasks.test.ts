import {expect, test} from 'vitest';
import {TaskInputError, taskCommand, taskIdentifier, taskText, taskTime, taskQuantity}
  from '../src/domain/tasks';

const revision = '9007199254740993';
const complete = {action: 'task.complete', occurrenceId: 'work-1', payload: {
  expected_revision: revision, performer_ids: ['member-1'], performed_at: '9223372036854775807',
  material_usages: [{line_id: 'line-1', quantity: '3.333333'}]}};

test('task creation preserves literal text and supplies no actor, household or permission', () => {
  const raw = {action: 'task.create', payload: {expected_revision: 0,
    title: '  Clean 🧹 <kitchen>  ', description: 'First\nthen\tsecond', priority: 'normal'}};
  const value = taskCommand(raw);
  expect(value).toEqual(raw); if (!value) throw Error('missing task');
  expect(Object.isFrozen(value)).toBe(true);
  expect(Object.isFrozen(value.payload)).toBe(true);
  expect(taskCommand({...raw, householdId: 'other'})).toBeUndefined();
});

test('completion takes an immutable copy of exact time, revision and material quantities', () => {
  const value = taskCommand(complete);
  expect(value).toEqual(complete); expect(value).not.toBe(complete);
  if (value?.action !== 'task.complete') throw Error('missing completion');
  expect(Object.isFrozen(value.payload.performer_ids)).toBe(true);
  expect(Object.isFrozen(value.payload.material_usages)).toBe(true);
  expect(Object.isFrozen(value.payload.material_usages![0])).toBe(true);
  expect(taskCommand({...complete, payload: {...complete.payload, material_usages: null}})).toBeDefined();
});

test.each(['task.claim', 'task.verify', 'task.reopen'] as const)('closed command %s preserves its original revision', action => {
  const payload = action === 'task.claim' ? {expected_revision: revision}
    : action === 'task.verify' ? {expected_revision: revision, cycle_id: 'cycle-1', decision: 'approved', reason: ''}
    : {expected_revision: revision, cycle_id: 'cycle-1', reason: 'Correct the recorded work'};
  expect(taskCommand({action, occurrenceId: 'work-1', payload})).toEqual({action, occurrenceId: 'work-1', payload});
});

test.each([null, undefined, [], {}, {action: 'future', payload: {}},
  {action: 'task.create', payload: {expected_revision: '0', title: 'A', description: '', priority: 'normal'}},
  {...complete, occurrenceId: '../other'}, {...complete, actor: 'other'},
  {...complete, payload: {...complete.payload, expected_revision: 1}},
  {...complete, payload: {...complete.payload, performed_at: 1}},
  {...complete, payload: {...complete.payload, performer_ids: []}},
  {...complete, payload: {...complete.payload, performer_ids: ['a', 'a']}},
  {...complete, payload: {...complete.payload, performer_ids: Array.from({length: 33}, (_, i) => `a${i}`)}},
  {...complete, payload: {...complete.payload, material_usages: [{line_id: 'line-1', quantity: '1.0'}]}},
  {...complete, payload: {...complete.payload, material_usages: [{line_id: 'line-1', quantity: '1'}, {line_id: 'line-1', quantity: '2'}]}},
  {action: 'task.verify', occurrenceId: 'work-1', payload: {expected_revision: '1', cycle_id: 'cycle-1', decision: 'pending', reason: ''}},
  {action: 'task.reopen', occurrenceId: 'work-1', payload: {expected_revision: '1', cycle_id: 'cycle-1', reason: ' '}}
])('unsupported task input %# fails without producing a request', value => {
  expect(taskCommand(value)).toBeUndefined();
});

test.each(['A', '  A  ', '\uFEFF', '😀'.repeat(160), '\u0085A', 'e\u0301'])(
  'task titles preserve accepted Unicode without trimming %j', value => expect(taskText(value, 160, true)).toBe(value));
test.each([null, 1, true, '', '  \u0085', '😀'.repeat(161), '\u0000A', 'A\u007f', '\ud800', 'A\nB'])(
  'invalid title %# is rejected', value => expect(() => taskText(value, 160, true)).toThrow(TaskInputError));
test('optional multiline descriptions accept only the task text control policy', () => {
  expect(taskText('', 4000, false, true)).toBe('');
  expect(taskText('A\tB\r\nC', 4000, false, true)).toBe('A\tB\r\nC');
  expect(() => taskText('A\u000bB', 4000, false, true)).toThrow('invalid_task_input');
});

test.each(['0', '1', '9007199254740993', '9223372036854775807'])(
  'task time preserves nonnegative int64 text %s', value => expect(taskTime(value)).toBe(value));
test.each([1, null, '', '-1', '+1', '01', '1.0', '1e2', '1\n', '9223372036854775808'])(
  'ambiguous task time %# is rejected', value => expect(() => taskTime(value)).toThrow(TaskInputError));
test.each(['0', '1', '0.1', '3.333333', '999999999999.999999'])(
  'canonical material quantity %s is accepted without rounding', value => expect(taskQuantity(value)).toBe(value));
test.each([1, null, '', '-1', '01', '.1', '1.0', '0.0000001', '1000000000000', '1\n'])(
  'ambiguous material quantity %# is rejected', value => expect(() => taskQuantity(value)).toThrow(TaskInputError));
test('task identifiers cannot become paths or caller-selected transport fields', () => {
  expect(taskIdentifier('A_b.c:d-1')).toBe('A_b.c:d-1');
  for (const value of [null, 1, '', '../work', 'a/b', 'x?owner=a', 'a'.repeat(129)])
    expect(() => taskIdentifier(value)).toThrow(TaskInputError);
});


test('rejection requires a real reason while an unknown targeted action never becomes a request', () => {
  expect(taskCommand({action: 'future', occurrenceId: 'work-1', payload: {}})).toBeUndefined();
  expect(taskCommand({action: 'task.verify', occurrenceId: 'work-1', payload: {expected_revision: '1', cycle_id: 'cycle-1', decision: 'rejected', reason: ''}})).toBeUndefined();
  expect(taskCommand({action: 'task.verify', occurrenceId: 'work-1', payload: {expected_revision: '1', cycle_id: 'cycle-1', decision: 'rejected', reason: 'Not performed'}})).toBeDefined();
});
