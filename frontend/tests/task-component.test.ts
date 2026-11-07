import {afterEach, expect, test} from 'vitest';
import {taskInstant, taskMessage} from '../src/presentation/task-messages';
import type {TaskRecord} from '../src/application/task-ports';
import type {TaskView} from '../src/application/task-controller';
import {revisionValue} from '../src/domain/administration';
import type {DomusTasks, TaskIntent} from '../src/presentation/domus-tasks';
import '../src/presentation/domus-tasks';
const revision = revisionValue('1');
const work = {occurrenceId: 'work-1', definitionId: 'def-1', definitionRevision: revision, title: '<b>Clean 🧹</b>', description: 'Wipe then dry',
  priority: 'normal' as const, state: 'available' as const, revision, assigneeIds: [], dueAt: null, currentCycleId: null,
  allowedActions: ['claim', 'complete'], cycle: null, materials: [], materialRecording: 'review_on_completion' as const, dependencyReviewRequired: false, pendingMaterials: false};
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
function view(patch: Partial<TaskView> = {}): TaskView {
  return {phase: 'ready', busy: false, session: {context, deployment: 'native', access: 'full', serverTime: 1000, expiresAt: 100000, householdApiAvailable: true},
    access: {householdId: 'private-home-id', memberId: 'private-member-id', canCreate: true, canReviewSchedule: true}, scopeKey: 'same-verified-scope',
    readOnly: false, page: {items: [work], nextCursor: null}, detail: null, records: [], outcome: null, notice: null, ...patch};
}
const mounted: DomusTasks[] = [];
afterEach(() => {for (const element of mounted.splice(0)) element.remove();});
async function mount(value: TaskView | null = view(), locale: 'en' | 'es' = 'en') {
  const element = document.createElement('domus-tasks'); element.view = value; element.language = locale;
  const intents: TaskIntent[] = []; element.addEventListener('domus-task-intent', event => intents.push((event as CustomEvent<TaskIntent>).detail));
  document.body.append(element); mounted.push(element); await element.updateComplete;
  const root = element.shadowRoot!, button = (label: string) => [...root.querySelectorAll('button')].find(value => value.textContent?.trim() === label)!;
  const input = async (id: string, value: string) => {const field = root.querySelector<HTMLInputElement>('#' + id)!;
    field.value = value; field.dispatchEvent(new InputEvent('input', {bubbles: true})); await element.updateComplete;};
  return {element, root, intents, button, input, text: () => root.textContent!};
}
test('usable task creation preserves literal input and emits one semantic intent', async () => {
  const f = await mount(); expect(f.root.querySelector<HTMLSelectElement>('#task-priority')!.value).toBe('normal');
  await f.input('task-title', '  Clean 🧹  '); await f.input('task-description', 'Wipe then dry');
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {bubbles: true, cancelable: true}));
  expect(f.intents).toEqual([{type: 'create', title: '  Clean 🧹  ', description: 'Wipe then dry', priority: 'normal'}]);
  expect(f.text()).not.toContain('private-home-id'); expect(f.text()).not.toContain('private-member-id');
});
test.each([['en', '', 'Enter a title.'], ['es', '   ', 'Introduce un título.']] as const)(
  'creation rejects a missing title locally in %s and preserves the other fields', async (locale, title, message) => {
    const f = await mount(view(), locale); f.root.querySelector<HTMLDetailsElement>('details.new-task')!.open = true;
    await f.input('task-title', title); await f.input('task-description', 'Keep this draft');
    const form = f.root.querySelector('form')!, field = f.root.querySelector<HTMLInputElement>('#task-title')!;
    expect(field.getAttribute('aria-invalid')).toBe('false');
    form.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); await f.element.updateComplete;
    expect(f.intents).toEqual([]); expect(f.root.activeElement).toBe(field);
    expect(field.getAttribute('aria-invalid')).toBe('true'); expect(f.text()).toContain(message);
    await f.input('task-title', 'Clean the filter');
    expect(field.getAttribute('aria-invalid')).toBe('false');
    form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
    expect(f.intents).toEqual([{type: 'create', title: 'Clean the filter', description: 'Keep this draft', priority: 'normal'}]);
  },
);
test('list content is inert, and selecting work opens its actual task rather than an invented route', async () => {
  const f = await mount(); expect(f.root.querySelector('b,script,img')).toBeNull();
  f.button('<b>Clean 🧹</b>').click(); expect(f.intents).toEqual([{type: 'select', occurrenceId: 'work-1'}]);
  expect(f.root.querySelector('a')).toBeNull();
});
test('completion and claiming use only the current server-derived affordances', async () => {
  const f = await mount(view({detail: work})); f.button('Claim task').click();
  f.root.querySelector<HTMLFormElement>('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([{type: 'claim'}, {type: 'complete', materialUsages: null}]);
  f.element.view = view({detail: {...work, allowedActions: []}}); await f.element.updateComplete;
  expect(f.button('Claim task')).toBeUndefined(); expect(f.button('Mark done now')).toBeUndefined();
});
test('restricted completion pending adult approval is explicit and review actions stay separate', async () => {
  const f = await mount(view({detail: {...work, state: 'completed', allowedActions: ['approve', 'reject', 'reopen'],
    cycle: {cycleId: 'cycle-1', verification: 'pending', performedAt: '1000', performerIds: ['member-1']}, dependencyReviewRequired: true, pendingMaterials: true}}), 'es');
  expect(f.text()).toContain('Pendiente de aprobación'); expect(f.text()).toContain('Los materiales necesitan revisión');
  await f.input('task-reason', 'Revisado'); f.button('Aprobar').click(); f.button('Rechazar').click(); f.button('Reabrir tarea').click();
  expect(f.intents).toEqual([{type: 'verify', decision: 'approved', reason: 'Revisado'}, {type: 'verify', decision: 'rejected', reason: 'Revisado'}, {type: 'reopen', reason: 'Revisado'}]);
});
test('read-only access and unconfirmed storage block mutations while task reads remain visible', async () => {
  for (const patch of [{readOnly: true}, {records: null}, {busy: true}]) {
    const f = await mount(view({...patch, detail: work}));
    expect(f.button('Create task').disabled).toBe(true); expect(f.button('Claim task').disabled).toBe(true);
    expect(f.text()).toContain('<b>Clean 🧹</b>');
  }
});
test('unverified/loading/closed states never render retained task content', async () => {
  for (const value of [null, view({phase: 'loading'}), view({phase: 'closed'}), view({access: null, notice: 'forbidden'})]) {
    const f = await mount(value); expect(f.text()).not.toContain('Clean 🧹'); expect(f.root.querySelector('input')).toBeNull();
  }
});
test('a same-owner recheck retains a draft; another verified scope and closure retire it', async () => {
  const f = await mount(); await f.input('task-title', 'Private draft'); f.element.view = view({phase: 'loading', scopeKey: null}); await f.element.updateComplete;
  f.element.view = view(); await f.element.updateComplete; expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('Private draft');
  f.element.view = view({scopeKey: 'other-verified-scope'}); await f.element.updateComplete; expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('');
});
test('pagination and refresh emit bounded read intents', async () => {
  const f = await mount(view({page: {items: [], nextCursor: 'opaque'}}));
  expect(f.text()).toContain('No tasks on this page'); f.button('Next page').click(); f.button('Refresh tasks').click();
  expect(f.intents).toEqual([{type: 'more'}, {type: 'refresh'}]);
});


test('task date formatting respects exact bounds and uses English fallback without inventing missing dates', () => {
  expect(taskMessage('title', 'fr')).toBe('Tasks'); expect(taskMessage('title', 'es-MX')).toBe('Tareas');
  expect(taskInstant(null, 'es')).toBe('Sin fecha de vencimiento'); expect(taskInstant('0', 'en')).toContain('UTC');
  for (const value of ['9223372036854775807', '-1', 'not-a-time']) expect(taskInstant(value, 'en')).toBe('Time unavailable');
});
test('choosing a priority retains the visible value across language changes', async () => {
  const f = await mount(); await f.input('task-title', 'Clean the filter'); const select = f.root.querySelector<HTMLSelectElement>('#task-priority')!;
  select.value = 'urgent'; select.dispatchEvent(new Event('change', {bubbles: true})); await f.element.updateComplete;
  f.element.language = 'es'; await f.element.updateComplete; expect(select.value).toBe('urgent');
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); expect(f.intents[0]).toMatchObject({priority: 'urgent'});
});
test('a saved creation clears only the unchanged draft that was submitted', async () => {
  const f = await mount(); await f.input('task-title', 'Submitted');
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  const saved = {kind: 'receipt' as const, stage: 'committed' as const, action: 'task.create' as const, operationId: 'op-1', occurrenceId: 'work-1',
    revision, state: 'available' as const, cycle: null, archivedBy: null};
  f.element.view = view({outcome: saved}); await f.element.updateComplete; expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('');
  await f.input('task-title', 'Newer draft'); f.element.view = view({outcome: {...saved, operationId: 'old-recovery'}}); await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('Newer draft');
  f.element.view = view({outcome: {...saved, stage: 'historical', archivedBy: 'restore-1'}}); await f.element.updateComplete;
  expect(f.text()).toContain('Its effect is absent from current state'); expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('Newer draft');
});
test('task material review accepts exact decimal input and zero without floating-point rounding', async () => {
  const f = await mount(view({detail: {...work, materials: [{lineId: 'cleaner', label: 'Cleaner', plannedQuantity: '1', precision: 6}, {lineId: 'cloth', label: '', plannedQuantity: '2', precision: 6}]}}), 'es');
  expect(f.root.activeElement?.id).toBe('selected-task-title');
  await f.input('material-0', '0003,3300'); await f.input('material-1', '0.000');
  f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([{type: 'complete', materialUsages: [{line_id: 'cleaner', quantity: '3.33'}, {line_id: 'cloth', quantity: '0'}]}]);
});
test.each([['en', '1.123456'], ['es', '1,123456']] as const)(
  'a precision-six material submits all six decimal places in %s', async (locale, input) => {
    const f = await mount(view({detail: {...work, materials: [{lineId: 'cleaner', label: 'Cleaner', plannedQuantity: '1', precision: 6}]}}), locale);
    await f.input('material-0', input);
    f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
    expect(f.intents).toEqual([{type: 'complete', materialUsages: [{line_id: 'cleaner', quantity: '1.123456'}]}]);
  });
test.each(['-1', '1e3', '', '1000000000000', '0.0000001', '1'.repeat(65)])(
  'unsupported material quantity %j focuses the actual invalid line and sends no command', async value => {
    const f = await mount(view({detail: {...work, materials: [{lineId: 'first', label: 'First', plannedQuantity: '1', precision: 6}, {lineId: 'second', label: 'Second', plannedQuantity: '1', precision: 6}]}}));
    await f.input('material-1', value); f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
    await f.element.updateComplete; expect(f.intents).toEqual([]); expect(f.root.activeElement?.id).toBe('material-1');
    expect(f.root.querySelector('#material-0')!.getAttribute('aria-invalid')).toBe('false');
    expect(f.root.querySelector('#quantity-error')!.getAttribute('role')).toBe('alert');
  });
test('separately recorded materials are not silently submitted as planned consumption', async () => {
  const f = await mount(view({detail: {...work, materialRecording: 'separate_recording', materials: [{lineId: 'first', label: 'Cleaner', plannedQuantity: '1', precision: 6}]}}));
  expect(f.text()).toContain('recorded separately'); expect(f.root.querySelector('[inputmode=decimal]')).toBeNull();
  f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); expect(f.intents).toEqual([{type: 'complete', materialUsages: null}]);
});
function savedRecord(stage: TaskRecord['stage']): TaskRecord {
  return {key: 'private-original-key', scope: {context, householdId: 'private-home', memberId: 'private-member'}, createdAt: 100, expiresAt: 3600100,
    command: {action: 'task.create', payload: {expected_revision: 0, title: 'Private original title', description: '', priority: 'normal'}}, stage,
    operationId: stage === 'committed' || stage === 'historical' ? 'op-1' : null};
}
test.each(['prepared', 'uncertain', 'committed', 'historical', 'rejected'] as const)(
  'saved %s request has explicit recovery/dismissal actions and no raw private payload', async stage => {
    const f = await mount(view({records: [savedRecord(stage)]}));
    expect(f.text()).not.toContain('private-original-key'); expect(f.text()).not.toContain('Private original title');
    expect(f.text()).not.toContain('private-home'); expect(f.text()).not.toContain(context.subject);
    if (stage !== 'rejected') {f.button('Check saved request').click(); expect(f.intents.at(-1)).toEqual({type: 'recover', key: 'private-original-key'});}
    if (stage !== 'prepared' && stage !== 'uncertain') {f.button('Dismiss saved request').click(); expect(f.intents.at(-1)).toEqual({type: 'dismiss', key: 'private-original-key'});}
    else expect(f.button('Create task').disabled).toBe(true);
  });
test.each(['uncertain', 'rejected'] as const)('visible %s outcomes explain impact without claiming success', async kind => {
  const f = await mount(view({outcome: kind === 'uncertain' ? {kind} : {kind, reason: 'conflict', correlationId: 'cor_private'}}));
  expect(f.root.querySelector('[role=status]')).not.toBeNull(); expect(f.text()).toContain(kind === 'uncertain' ? 'Result not confirmed' : 'Change not accepted');
  expect(f.text()).not.toContain('cor_private');
});
test('an invalid creation or review focuses its corresponding field; retired views erase draft text', async () => {
  const f = await mount(); f.element.view = view({notice: 'invalid_input'}); await f.element.updateComplete; expect(f.root.activeElement?.id).toBe('task-title');
  f.element.view = view({detail: {...work, allowedActions: ['reopen']}}); await f.element.updateComplete; await f.input('task-reason', 'Private draft');
  f.button('Reopen task').click(); f.element.view = view({detail: {...work, allowedActions: ['reopen']}, notice: 'invalid_input'}); await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('task-reason'); f.element.retired = true; await f.element.updateComplete;
  expect(f.root.querySelector('input,textarea')).toBeNull(); f.element.retired = false; f.element.view = view(); await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('');
});
test('a pending event and a manually dispatched disabled form cannot request a mutation', async () => {
  const f = await mount(view({busy: true, detail: work})); await f.input('task-title', 'Clean the filter');
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); expect(f.intents).toEqual([]);
  f.element.view = view({records: null, detail: work}); await f.element.updateComplete;
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); expect(f.intents).toEqual([]);
  f.element.view = view({phase: 'closed'}); await f.element.updateComplete;
  f.root.querySelector('button')!.dispatchEvent(new MouseEvent('click')); expect(f.intents).toEqual([]);
});


test('whole-unit materials refuse fractional quantities before completion', async () => {
  const f = await mount(view({detail: {...work, materials: [{lineId: 'unit', label: 'Cloth', plannedQuantity: '1', precision: 0}]}}));
  expect(f.text()).toContain('Use whole quantities'); await f.input('material-0', '0.5');
  f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); await f.element.updateComplete;
  expect(f.intents).toEqual([]); expect(f.root.activeElement?.id).toBe('material-0');
});
test('an unexpected unreviewed material line never substitutes its planned amount as actual usage', async () => {
  const f = await mount(view({detail: {...work, description: ''}}));
  f.element.view = view({detail: {...work, description: '', materials: [{lineId: 'new-line', label: 'New material', plannedQuantity: '2', precision: 6}]}});
  await f.element.updateComplete; expect(f.root.querySelector<HTMLInputElement>('#material-0')!.value).toBe('');
  f.root.querySelector('#complete-form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); await f.element.updateComplete;
  expect(f.intents).toEqual([]); expect(f.root.querySelector('.description')).toBeNull();
});
test('a member without creation permission sees task reads; an unavailable list never claims an empty household', async () => {
  const f = await mount(view({access: {householdId: 'home', memberId: 'member-1', canCreate: false, canReviewSchedule: false}, page: null, notice: 'unavailable'}));
  expect(f.root.querySelector('form')).toBeNull(); expect(f.text()).not.toContain('No tasks on this page'); expect(f.text()).toContain('Tasks could not be loaded');
});

test.each(['a', '🧹'])('creation enforces Unicode code-point bounds without losing the draft (%s)', async character => {
  const f = await mount(); f.root.querySelector<HTMLDetailsElement>('details.new-task')!.open = true; const form = f.root.querySelector('form')!;
  await f.input('task-title', character.repeat(161));
  expect(f.root.querySelector('#task-title')!.getAttribute('aria-invalid')).toBe('true');
  expect(f.button('Create task').disabled).toBe(true);
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]); expect(f.root.activeElement?.id).toBe('task-title');
  expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe(character.repeat(161));
  await f.input('task-title', character.repeat(160)); await f.input('task-description', character.repeat(4001));
  expect(f.root.querySelector('#task-description')!.getAttribute('aria-invalid')).toBe('true');
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]); expect(f.root.activeElement?.id).toBe('task-description');
  await f.input('task-description', character.repeat(4000)); expect(f.button('Create task').disabled).toBe(false);
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([{type: 'create', title: character.repeat(160), description: character.repeat(4000), priority: 'normal'}]);
});
test.each(['a', '🧹'])('review enforces the same 1,000-code-point reason bound (%s)', async character => {
  const f = await mount(view({detail: {...work, state: 'completed', allowedActions: ['approve', 'reject', 'reopen'],
    cycle: {cycleId: 'cycle-1', verification: 'pending', performedAt: '1000', performerIds: ['member-1']}}}));
  await f.input('task-reason', character.repeat(1001));
  expect(f.root.querySelector('#task-reason')!.getAttribute('aria-invalid')).toBe('true');
  for (const label of ['Approve', 'Reject', 'Reopen task']) expect(f.button(label).disabled).toBe(true);
  await f.input('task-reason', character.repeat(1000));
  expect(f.button('Reject').disabled).toBe(false); f.button('Reject').click();
  expect(f.intents).toEqual([{type: 'verify', decision: 'rejected', reason: character.repeat(1000)}]);
});


test.each(['en', 'es'] as const)('required review reasons prevent impossible actions in %s', async locale => {
  const labels = locale === 'es' ? ['Aprobar', 'Rechazar', 'Reabrir tarea'] : ['Approve', 'Reject', 'Reopen task'];
  const f = await mount(view({detail: {...work, state: 'completed', allowedActions: ['approve', 'reject', 'reopen']}}), locale);
  for (const reason of ['', '\u0085', ' \t\n ']) {
    await f.input('task-reason', reason);
    expect(f.button(labels[0]).disabled).toBe(false);
    for (const label of labels.slice(1)) {expect(f.button(label).disabled).toBe(true); f.button(label).click();}
    expect(f.intents).toEqual([]);
  }
  f.button(labels[0]).click();
  expect(f.intents).toEqual([{type: 'verify', decision: 'approved', reason: ' \t\n '}]);
  await f.input('task-reason', '  Correct the completion  ');
  for (const label of labels.slice(1)) {expect(f.button(label).disabled).toBe(false); f.button(label).click();}
  expect(f.intents.slice(1)).toEqual([{type: 'verify', decision: 'rejected', reason: '  Correct the completion  '},
    {type: 'reopen', reason: '  Correct the completion  '}]);
});
