import {expect, test} from 'vitest';
import {TaskSessionJournal, TASK_JOURNAL_KEY} from '../src/adapters/task-journal';
import type {OwnedStorage} from '../src/adapters/session-journal';
import {taskCommand} from '../src/domain/tasks';
import {TaskSessionJournal as Edge57Journal, TaskController as Edge57Controller,
  TASK_JOURNAL_KEY as EDGE57_KEY} from './fixtures/edge57-task-journal.mjs';
import {vi} from 'vitest';
import type {TaskServer} from '../src/application/task-ports';
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const scope = {context, householdId: 'home', memberId: 'member-1'};
const command = taskCommand({action: 'task.create', payload: {expected_revision: 0, title: '  Clean 🧹  ', description: '', priority: 'normal'}})!;

test.each(['ordinary-materials','scheduled-materials','settlement'])(
  'actual Edge.57 client preserves opaque %s bytes and blocks writes until re-upgrade', async kind => {
    expect(EDGE57_KEY).toBe(TASK_JOURNAL_KEY);
    const key='domus-150-owned-rollback-'+kind+':'+TASK_JOURNAL_KEY;
    const storage:OwnedStorage={getItem:name=>sessionStorage.getItem('domus-150-owned-rollback-'+kind+':'+name),
      setItem:(name,value)=>sessionStorage.setItem('domus-150-owned-rollback-'+kind+':'+name,value),
      removeItem:name=>sessionStorage.removeItem('domus-150-owned-rollback-'+kind+':'+name)};
    expect(sessionStorage.getItem(key)).toBeNull();
    try {
      const journal=new TaskSessionJournal(storage);journal.open(scope,100);
      for(let i=0;i<7;i++){journal.prepare('legacy-'+i,command,101+i*2);journal.record('legacy-'+i,'committed','legacy-operation-'+i,102+i*2);}
      const legacy=new Edge57Journal(storage).open(scope,200);
      expect(legacy).toHaveLength(7);journal.open(scope,201);
      const current=kind==='settlement'?taskCommand({action:'task.material.settle',occurrenceId:'work-1',intentId:'intent-1',
        payload:{expected_revision:'7',cycle_id:'cycle-1',action:'correct',quantity:'0',reason:'Initially unrecorded'}})!
        :taskCommand({...command,payload:{...command.payload,materials:[{reference_id:'soap-reference',planned_quantity:'1.25'}],
          ...kind==='scheduled-materials'?{schedule:{draft:{kind:'fixed',start:{kind:'date',local:'2027-01-02'},rrule:'FREQ=DAILY'},
            policy:{zone:'UTC',data_identity:'tzdata:2026.6/iana:2026f',repeated_time:'first_instant',revision:'1'}}}:{}}})!;
      expect(current).toBeDefined();journal.prepare('material-original',current,202);journal.record('material-original','uncertain',null,203);
      const raw=sessionStorage.getItem(key);
      expect(()=>new Edge57Journal(storage).open(scope,204)).toThrow('invalid_journal');
      expect(sessionStorage.getItem(key)).toBe(raw);
      const read=<T>(value:T)=>({result:Promise.resolve(value),cancel:vi.fn()});
      const server:TaskServer={access:()=>read({householdId:'home',memberId:'member-1',canCreate:true,canReviewSchedule:false}),
        list:()=>read({items:[],nextCursor:null}),detail:vi.fn(),original:vi.fn(),send:vi.fn()};
      const prior=new Edge57Controller('native',{session:()=>read({context,deployment:'native',access:'full',serverTime:1000,expiresAt:100000,householdApiAvailable:true})},
        server,new Edge57Journal(storage),{anchor:()=>{},now:()=>1000},{requestKey:vi.fn()});
      await prior.refresh();expect(prior.view.records).toBeNull();expect(prior.view.notice).toBe('journal_unavailable');
      await prior.create('Must remain blocked','','normal');expect(server.send).not.toHaveBeenCalled();prior.close();
      expect(sessionStorage.getItem(key)).toBe(raw);
      const upgraded=new TaskSessionJournal(storage),records=upgraded.open(scope,1001);
      expect(records.slice(0,7)).toEqual(legacy);expect(records[7]).toMatchObject({key:'material-original',command:current,stage:'uncertain',operationId:null,createdAt:202,expiresAt:3600202});
      expect(()=>upgraded.prepare('ninth',command,1002)).toThrow('journal_capacity');
      upgraded.open(scope,1003);expect(()=>upgraded.forget('material-original',1004)).toThrow('unresolved_request');
      upgraded.open(scope,1005);expect(upgraded.record('material-original','historical','material-operation',1006)[7].command).toEqual(current);
      upgraded.forget('legacy-0',1007);expect(upgraded.prepare('after-explicit-dismissal',command,1008)).toHaveLength(8);
    } finally {sessionStorage.removeItem(key);}
  });
function fixture() {
  const data = new Map<string, string>();
  const storage: OwnedStorage = {getItem: key => data.get(key) ?? null, setItem: (key, value) => {data.set(key, value);}, removeItem: key => {data.delete(key);}};
  return {data, storage, journal: new TaskSessionJournal(storage)};
}
test('progress and prior creation and assignment requests coexist with their frozen bodies', () => {
  const f = fixture();
  f.journal.open(scope, 100);
  f.journal.prepare('create', command, 100);
  f.journal.record('create', 'committed', 'create-operation', 101);
  const assignment = taskCommand({action: 'task.assign', occurrenceId: 'work-1',
    payload: {expected_revision: '1', assignee_ids: ['member-1']}})!;
  f.journal.prepare('assignment', assignment, 102);
  f.journal.record('assignment', 'committed', 'assignment-operation', 103);
  const progress = taskCommand({action: 'task.transition', occurrenceId: 'work-1',
    payload: {expected_revision: '9007199254740993', target: 'blocked', reason: 'Waiting\n🧰'}})!;
  f.journal.prepare('progress', progress, 104);
  f.journal.record('progress', 'uncertain', null, 105);
  const reopened = new TaskSessionJournal(f.storage).open(scope, 106);
  expect(reopened.map(record => record.command)).toEqual([command, assignment, progress]);
  expect(reopened[2]).toMatchObject({key: 'progress', scope, stage: 'uncertain', operationId: null});
  expect(Object.isFrozen(reopened[2].command.payload)).toBe(true);
  expect(new TaskSessionJournal(f.storage).open({...scope, memberId: 'other'}, 107)).toEqual([]);
});
test('assignment and older creation originals coexist across reload with frozen identities', () => {
  const f = fixture(); f.journal.open(scope, 100);
  f.journal.prepare('older-create', command, 100);
  const assignment = taskCommand({action: 'task.assign', occurrenceId: 'work-1',
    payload: {expected_revision: '9007199254740993', assignee_ids: ['member-2', 'member-1']}})!;
  f.journal.prepare('assignment', assignment, 101);
  f.journal.record('assignment', 'uncertain', null, 102);
  const records = new TaskSessionJournal(f.storage).open(scope, 103);
  expect(records[0].command).toEqual(command);
  expect(records[1]).toMatchObject({key: 'assignment', scope, stage: 'uncertain', command: assignment});
  expect(Object.isFrozen((records[1].command.payload as {assignee_ids: readonly string[]}).assignee_ids)).toBe(true);
  expect(f.journal.open({...scope, householdId: 'foreign'}, 104)).toEqual([]);
});
test('task originals survive a reload without changing key, text, scope, stage or expiry', () => {
  const f = fixture(); expect(f.journal.open(scope, 100)).toEqual([]);
  const original = f.journal.prepare('original', command, 101)[0];
  expect(original.command).toEqual(command); expect(original.expiresAt).toBe(3600101);
  expect(Object.isFrozen(original)).toBe(true);
  f.journal.record('original', 'uncertain', null, 102); f.journal.detach();
  const reopened = new TaskSessionJournal(f.storage).open(scope, 200)[0];
  expect(reopened).toEqual({...original, stage: 'uncertain'});
  expect([...f.data.keys()]).toEqual([TASK_JOURNAL_KEY]);
  expect(f.data.get(TASK_JOURNAL_KEY)).not.toMatch(/csrf|token|cookie/u);
});
test('each verified installation, channel, account, household and member has a private view', () => {
  const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('original', command, 100);
  for (const next of [{...scope, householdId: 'other'}, {...scope, memberId: 'other'},
    {...scope, context: {...context, subject: 'b'.repeat(32)}}, {...scope, context: {...context, channel: 'stable' as const}},
    {...scope, context: {...context, installationId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}}]) {
    expect(f.journal.open(next, 101)).toEqual([]);
  }
  expect(f.journal.open(scope, 102)).toHaveLength(1);
});
test('unresolved originals cannot be discarded, rebound or evicted to make capacity', () => {
  const f = fixture(); f.journal.open(scope, 100);
  for (let i = 0; i < 8; i++) f.journal.prepare('key-' + i, command, 100);
  expect(() => f.journal.prepare('ninth', command, 100)).toThrow('journal_capacity');
  f.journal.open(scope, 100);
  expect(() => f.journal.forget('key-0', 100)).toThrow('unresolved_request');
  f.journal.open(scope, 100);
  expect(() => f.journal.prepare('key-0', command, 100)).toThrow();
});
test('a recovered operation keeps its identity and may later become historical', () => {
  const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('original', command, 100);
  f.journal.record('original', 'committed', 'op-1', 101);
  expect(f.journal.record('original', 'historical', 'op-1', 102)[0].stage).toBe('historical');
  expect(() => f.journal.record('original', 'committed', 'other', 103)).toThrow('original_operation_changed');
  f.journal.open(scope, 103); expect(f.journal.forget('original', 103)).toEqual([]);
});
test('expiry does not renew across reopen and clock rollback cannot hide original evidence', () => {
  const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('original', command, 100);
  expect(() => f.journal.open(scope, 99)).toThrow('invalid_journal_time');
  expect(f.journal.open(scope, 3600100)).toEqual([]);
});
test('unsupported storage is a visible refusal to prepare a write', () => {
  expect(() => new TaskSessionJournal(undefined).open(scope, 100)).toThrow('storage_unavailable');
  const f = fixture(); expect(() => f.journal.prepare('key', command, 100)).toThrow('journal_not_open');
  f.data.set(TASK_JOURNAL_KEY, '{"version":1,"version":2}');
  expect(() => f.journal.open(scope, 100)).toThrow('invalid_journal');
});
test('cross-tab changes and unconfirmed writes do not report persistence success', () => {
  const f = fixture(); f.journal.open(scope, 100); f.data.set(TASK_JOURNAL_KEY, 'changed');
  expect(() => f.journal.prepare('key', command, 100)).toThrow('storage_changed');
  const discard: OwnedStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
  expect(() => new TaskSessionJournal(discard).open(scope, 100)).toThrow('storage_unconfirmed');
});


test.each([null, true, {}, [], -1, 1.5, Number.MAX_SAFE_INTEGER + 1])('invalid journal clock %# never rewrites existing data', value => {
  const f = fixture(); expect(() => f.journal.open(scope, value as number)).toThrow('invalid_journal_time'); expect(f.data.size).toBe(0);
});
test('a duplicate key cannot replace the original command before capacity is reached', () => {
  const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('original', command, 100); const prior = f.data.get(TASK_JOURNAL_KEY);
  expect(() => f.journal.prepare('original', command, 101)).toThrow('duplicate_request'); expect(f.data.get(TASK_JOURNAL_KEY)).toBe(prior);
});
test.each(['syntax', 'oversized_text', 'oversized_utf8', 'namespace', 'version', 'duplicate_record', 'future_record', 'changed_expiry',
  'invalid_stage', 'prepared_operation', 'missing_known_operation', 'unknown_command'])(
  'corrupt task recovery input %s fails without clearing or repairing its original bytes', kind => {
    const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('original', command, 100);
    const raw = f.data.get(TASK_JOURNAL_KEY)!, data = JSON.parse(raw);
    if (kind === 'namespace') data.namespace = 'administration';
    if (kind === 'version') data.version = 2;
    if (kind === 'duplicate_record') data.records.push(data.records[0]);
    if (kind === 'future_record') data.records[0].createdAt = 101;
    if (kind === 'changed_expiry') data.records[0].expiresAt++;
    if (kind === 'invalid_stage') data.records[0].stage = 'future';
    if (kind === 'prepared_operation') data.records[0].operationId = 'forged';
    if (kind === 'missing_known_operation') data.records[0].stage = 'committed';
    if (kind === 'unknown_command') data.records[0].command.action = 'future';
    const corrupted = kind === 'syntax' ? '{' : kind === 'oversized_text' ? ' '.repeat(65537)
      : kind === 'oversized_utf8' ? '😀'.repeat(17000) : JSON.stringify(data);
    f.data.set(TASK_JOURNAL_KEY, corrupted); expect(() => f.journal.open(scope, 101)).toThrow(); expect(f.data.get(TASK_JOURNAL_KEY)).toBe(corrupted);
  });
test('the journal enforces UTF-8 capacity without evicting earlier resolved or uncertain work', () => {
  const f = fixture(), large = taskCommand({action: 'task.create', payload: {expected_revision: 0, title: 'New', description: '😀'.repeat(4000), priority: 'normal'}})!;
  f.journal.open(scope, 100); for (let i = 0; i < 3; i++) f.journal.prepare('key-' + i, large, 100);
  const prior = f.data.get(TASK_JOURNAL_KEY); expect(() => f.journal.prepare('too-large', large, 100)).toThrow('journal_too_large');
  expect(f.data.get(TASK_JOURNAL_KEY)).toBe(prior);
});
test('unavailable and malformed providers never establish a confirmed recovery record', () => {
  for (const getItem of [() => {throw Error('private fault');}, () => undefined as never]) {
    const f = fixture(); expect(() => new TaskSessionJournal({...f.storage, getItem}).open(scope, 100)).toThrow('storage_unavailable');
  }
  const f = fixture(); expect(() => new TaskSessionJournal({...f.storage, setItem: () => {throw Error('private fault');}}).open(scope, 100)).toThrow('storage_unavailable');
});
test('only an existing resolved request may be dismissed, and outcomes cannot reset to prepared', () => {
  const f = fixture(); f.journal.open(scope, 100); expect(() => f.journal.forget('missing', 100)).toThrow('request_not_found');
  f.journal.open(scope, 100); f.journal.prepare('original', command, 100);
  expect(() => f.journal.record('original', 'prepared' as never, null, 100)).toThrow('invalid_journal');
  f.journal.open(scope, 100); f.journal.record('original', 'uncertain', null, 100);
  expect(() => f.journal.forget('original', 100)).toThrow('unresolved_request');
  f.journal.open(scope, 100); f.journal.record('original', 'rejected', null, 100); expect(f.journal.forget('original', 100)).toEqual([]);
});


test('recovering one request preserves every independent original unchanged', () => {
  const f = fixture(); f.journal.open(scope, 100); f.journal.prepare('first', command, 100);
  const second = f.journal.prepare('second', command, 101)[1];
  const current = f.journal.record('first', 'committed', 'op-1', 102);
  expect(current[0].stage).toBe('committed'); expect(current[1]).toEqual(second);
});
