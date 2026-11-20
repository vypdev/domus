import {expect, test, vi} from 'vitest';
import {TaskMaterialPlanning} from '../src/application/task-material-planning';
import type {InventoryServer} from '../src/application/inventory-controller';
import type {BaseUnit, InventoryReport} from '../src/domain/inventory';
import {EntryReadError} from '../src/application/ports';
const context = {installationId:'01234567-89ab-cdef-0123-456789abcdef', channel:'edge' as const, subject:'a'.repeat(32)};
const scope = {key:'same-owner', context, readOnly:false, canLink:true};
function report(ids: readonly string[], cursor: string | null = null, unit: BaseUnit = 'gram'): InventoryReport {
  return {mayManage:true, mayShop:true, mayRequest:true, cursor, locations:[], products:ids.map(id => ({id, referenceId:id,
    name:'Private ' + id, unit, recorded:'0', reserved:'0', available:'0', outstandingPurchase:'0', shoppingNeeded:'0',
    replenishment:{sourceId:'policy-' + id, minimum:'0', target:'0', revision:'0', needed:'0'}}))};
}
function fixture() {
  const read = vi.fn<InventoryServer['read']>(() => ({result:Promise.resolve(report([])), cancel:vi.fn()}));
  return {read, planner:new TaskMaterialPlanning({read})};
}
test('title-only creation does not read Inventory; later pages retain all exact selected quantities', async () => {
  const {read, planner} = fixture();
  await planner.load(); planner.bind(scope);
  expect(planner.selections()).toBeUndefined(); expect(read).not.toHaveBeenCalled();
  await planner.load(true); expect(read).not.toHaveBeenCalled();
  read.mockReturnValueOnce({result:Promise.resolve(report(['first'], 'next')), cancel:vi.fn()});
  await planner.load(); planner.add('first'); planner.edit('first', '000,000000');
  expect(planner.selections()).toEqual([{reference_id:'first', planned_quantity:'0'}]);
  read.mockReturnValueOnce({result:Promise.resolve(report(['later'], null, 'piece')), cancel:vi.fn()});
  await planner.load(true); planner.add('later'); planner.edit('later', '2');
  expect(read.mock.calls.map(([, cursor]) => cursor)).toEqual([null, 'next']);
  expect(planner.selections()).toEqual([{reference_id:'first', planned_quantity:'0'}, {reference_id:'later', planned_quantity:'2'}]);
  planner.edit('later', '0.1'); expect(planner.selections()).toBeNull();
  planner.edit('later', '0'); planner.edit('first', '1.000001');
  expect(planner.selections()?.[0].planned_quantity).toBe('1.000001');
  expect(planner.draftKey).toBe('[["first","1.000001"],["later","0"]]');
  planner.remove('later'); expect(planner.view.rows).toHaveLength(1);
  planner.clear(); expect(planner.view.open).toBe(false); expect(planner.selections()).toBeUndefined();
});
test('grant loss hides labels and retains opaque intent until explicit removal or current catalog review', async () => {
  const {read, planner} = fixture(); planner.bind(scope);
  read.mockReturnValueOnce({result:Promise.resolve(report(['private'])), cancel:vi.fn()});
  await planner.load(); planner.add('private'); planner.edit('private', '2.5');
  planner.bind({...scope, canLink:false});
  expect(planner.view.rows).toEqual([{referenceId:'private', input:'2.5', choice:null}]);
  expect(planner.view.choices).toEqual([]); expect(planner.selections()).toBeNull();
  await planner.load(); expect(read).toHaveBeenCalledTimes(1);
  planner.add('private'); expect(planner.view.notice).toBe('invalid_input');
  planner.bind(scope); await planner.load(); expect(planner.selections()).toBeNull();
  read.mockReturnValueOnce({result:Promise.resolve(report(['private'])), cancel:vi.fn()});
  await planner.load(); expect(planner.selections()).toEqual([{reference_id:'private', planned_quantity:'2.5'}]);
  planner.bind({...scope, canLink:false}); planner.remove('private'); expect(planner.selections()).toBeUndefined();
});
test('removing one denied line retains the recovery explanation until the whole plan is removed', async () => {
  const {read, planner} = fixture(); planner.bind(scope);
  read.mockReturnValueOnce({result:Promise.resolve(report(['first', 'second'])), cancel:vi.fn()});
  await planner.load(); planner.add('first'); planner.add('second');
  planner.bind({...scope, canLink:false}); planner.remove('first');
  expect(planner.view.notice).toBe('forbidden'); expect(planner.selections()).toBeNull();
  expect(planner.view.rows).toEqual([{referenceId:'second', input:'1', choice:null}]);
  planner.remove('second'); expect(planner.view.notice).toBeNull(); expect(planner.selections()).toBeUndefined();
});
test('refresh retires stale choices and reviews later-page selections without truncating the plan', async () => {
  const {read, planner} = fixture(); planner.bind(scope);
  read.mockReturnValueOnce({result:Promise.resolve(report(['later'])), cancel:vi.fn()});
  await planner.load(); planner.add('later');
  read.mockReturnValueOnce({result:Promise.resolve(report(['first'], 'next')), cancel:vi.fn()});
  await planner.load(); expect(planner.view.rows[0].choice).toBeNull(); expect(planner.selections()).toBeNull();
  read.mockReturnValueOnce({result:Promise.resolve(report(['later'])), cancel:vi.fn()});
  await planner.load(true); expect(planner.view.rows[0].choice?.name).toBe('Private later');
  expect(planner.selections()).toEqual([{reference_id:'later', planned_quantity:'1'}]);
});
test('the plan admits 32 distinct products across bounded pages and never silently drops a row', async () => {
  const {read, planner} = fixture(); planner.bind(scope);
  const ids = Array.from({length:33}, (_, index) => 'p' + index);
  read.mockReturnValueOnce({result:Promise.resolve(report(ids.slice(0,25), 'last')), cancel:vi.fn()});
  await planner.load(); ids.slice(0,25).forEach(id => planner.add(id)); planner.add('p0');
  expect(planner.view.notice).toBe('invalid_input'); expect(planner.view.rows).toHaveLength(25);
  read.mockReturnValueOnce({result:Promise.resolve(report(ids.slice(25))), cancel:vi.fn()});
  await planner.load(true); ids.slice(25).forEach(id => planner.add(id));
  expect(planner.view.rows).toHaveLength(32); expect(planner.selections()).toHaveLength(32);
  expect(planner.view.notice).toBe('invalid_input');
  planner.bind({...scope, readOnly:true}); planner.add('p32'); expect(planner.view.rows).toHaveLength(32);
  planner.bind({...scope, key:'other-owner'}); expect(planner.view.rows).toEqual([]);
  planner.bind(null); expect(planner.view.canLink).toBe(false);
});
test.each(['forbidden','authentication_required','unavailable','invalid_response', 'unexpected'])(
  'catalog %s never turns a retained plan into title-only creation', async error => {
    const {read, planner} = fixture(); planner.bind(scope);
    read.mockReturnValueOnce({result:Promise.resolve(report(['private'])), cancel:vi.fn()});
    await planner.load(); planner.add('private');
    read.mockReturnValueOnce({result:Promise.reject(error === 'unexpected' ? Error() : new EntryReadError(error as 'forbidden')), cancel:vi.fn()});
    await planner.load();
    expect(planner.view.rows).toEqual([{referenceId:'private', input:'1', choice:null}]);
    expect(planner.view.notice).toBe(error === 'forbidden' || error === 'authentication_required' ? 'forbidden' : 'unavailable');
    expect(planner.selections()).toBeNull();
  });
test('a live read-only catalog response cannot supply linking authority', async () => {
  const {read, planner} = fixture(); planner.bind(scope);
  read.mockReturnValueOnce({result:Promise.resolve({...report(['private']), mayManage:false}), cancel:vi.fn()});
  await planner.load(); expect(planner.view.notice).toBe('forbidden'); expect(planner.view.choices).toEqual([]);
});
test.each([false, true])('cancelled catalog completion (%s rejection) never repopulates a retired account', async reject => {
  const {read, planner} = fixture(); planner.bind(scope);
  let resolve!: (value:InventoryReport) => void, fail!: (error:unknown) => void;
  const cancel = vi.fn(() => {throw Error('cancel failed');});
  read.mockReturnValueOnce({result:new Promise((yes,no) => {resolve=yes;fail=no;}), cancel});
  const pending = planner.load(); await planner.load(); expect(read).toHaveBeenCalledTimes(1);
  planner.bind({...scope, key:'other-account'}); expect(cancel).toHaveBeenCalledOnce();
  if (reject) fail(new EntryReadError('forbidden')); else resolve(report(['private']));
  await pending; expect(planner.view.choices).toEqual([]); expect(planner.view.busy).toBe(false);
});
