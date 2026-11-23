import {afterEach, expect, test, vi} from 'vitest';
import type {HaTextField} from '@vypdev/ha-ui/field';
import type {HaCheckbox} from '@vypdev/ha-ui/checkbox';
import type {HaButton} from '@vypdev/ha-ui/button';
import type {HaFeedback} from '@vypdev/ha-ui/feedback';
import type {AdministrationView} from '../src/application/administration-controller';
import {taskInstant, taskMessage} from '../src/presentation/task-messages';
import {materialMessage} from '../src/presentation/task-material-messages';
import type {TaskRecord} from '../src/application/task-ports';
import type {TaskView} from '../src/application/task-controller';
import type {TaskDetail, TaskReceipt} from '../src/domain/tasks';
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
    readOnly: false, page: {items: [work], nextCursor: null}, detail: null, materialHistory:null, records: [], outcome: null, notice: null, ...patch};
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

for (const notice of ['unavailable','invalid_response'] as const)
test.each(['en','es'] as const)('%s missing post-create facts focus recovery once and preserve later draft editing ('+notice+')', async locale => {
  const f=await mount(view({notice}),locale);
  expect(f.root.activeElement).toBe(f.button(locale==='en'?'Refresh tasks':'Actualizar tareas'));
  f.root.querySelector<HTMLElement>('details.new-task summary')!.click();
  await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));await f.element.updateComplete;
  await f.input('task-title','A new retained draft');
  const title=f.root.querySelector<HTMLInputElement>('#task-title')!;title.focus();
  f.element.view=view({notice});await f.element.updateComplete;
  expect(f.root.activeElement).toBe(title);expect(title.value).toBe('A new retained draft');
});

test('a failed read with a selected task keeps its current detail focus', async () => {
  const f=await mount(view({detail:work}));const heading=f.root.querySelector<HTMLElement>('#selected-task-title')!;heading.focus();
  f.element.view=view({detail:work,notice:'unavailable'});await f.element.updateComplete;
  expect(f.root.activeElement).toBe(heading);
});

test('retired task data cannot move focus to a read recovery control', async () => {
  const f=await mount();const outside=document.createElement('button');outside.textContent='Outside task view';document.body.append(outside);
  try {
    outside.focus();f.element.retired=true;f.element.view=view({notice:'unavailable'});await f.element.updateComplete;
    expect(document.activeElement).toBe(outside);
  } finally {outside.remove();}
});

test('optional plan intents survive read loading and block a stale plan without losing task text', async () => {
  const plan = {open:false,busy:false,canLink:true,readOnly:false,rows:[],choices:[],cursor:null,notice:null} as const;
  const f = await mount(view({page:{items:[],nextCursor:null},materialPlan:plan}));
  await f.input('task-title','Retain this material task');
  const component = () => f.root.querySelector('domus-task-material-plan')!;
  await component().updateComplete;
  const open = component().shadowRoot!.querySelector<HaButton>('vyp-ha-button')!;
  await open.updateComplete; open.click();
  expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'load'});
  f.element.view=view({phase:'loading',busy:true,access:null,materialPlan:plan}); await f.element.updateComplete;
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...plan,open:true,notice:'unavailable'}});
  await f.element.updateComplete; await component().updateComplete; await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
  const retry=component().shadowRoot!.querySelector<HaButton>('vyp-ha-button')!;
  await retry.updateComplete; retry.click();
  expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'load'});
  const choice={referenceId:'soap',name:'Soap',unit:'piece' as const};
  const loaded={...plan,open:true,choices:[choice]};
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:loaded}); await f.element.updateComplete;
  await component().updateComplete; await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
  expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('Retain this material task');
  const select=component().shadowRoot!.querySelector('vyp-ha-select')!;
  expect(component().shadowRoot!.activeElement).toBe(select);
  select.dispatchEvent(new CustomEvent('ha-select-request',{detail:{value:'soap'}}));
  expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'add',referenceId:'soap'});
  const row={referenceId:'soap',input:'1',choice};
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...loaded,rows:[row]}});
  await f.element.updateComplete; await component().updateComplete; await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
  const field=component().shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!;
  field.dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'0'}}));
  expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'edit',referenceId:'soap',input:'0'});
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...loaded,rows:[{...row,input:'0'}]}}); await f.element.updateComplete;
  f.button('Create task').click(); expect(f.intents.at(-1)).toMatchObject({type:'create',title:'Retain this material task'});
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...loaded,rows:[{...row,input:'0.25',choice:{...choice,unit:'millilitre'}}]}}); await f.element.updateComplete;
  expect(f.button('Create task').disabled).toBe(false);
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...loaded,canLink:false,rows:[{...row,choice:null}]}}); await f.element.updateComplete;
  expect(f.button('Create task').disabled).toBe(true);
  f.root.querySelector<HTMLFormElement>('details.new-task form')!.dispatchEvent(new SubmitEvent('submit',{cancelable:true}));
  expect(f.root.querySelector<HTMLInputElement>('#task-title')!.value).toBe('Retain this material task');
  await component().updateComplete;
  const remove=[...component().shadowRoot!.querySelectorAll<HaButton>('vyp-ha-button')].find(button=>button.state.label==='Remove material')!;
  await remove.updateComplete; remove.click(); expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'remove',referenceId:'soap'});
  f.element.view=view({page:{items:[],nextCursor:null},materialPlan:{...loaded,rows:[]}}); await f.element.updateComplete;
  f.element.remove(); await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
});

test('starting a material read before native toggle delivery preserves the newly opened task editor', async () => {
  const plan={open:false,busy:false,canLink:true,readOnly:false,rows:[],choices:[],cursor:null,notice:null} as const;
  const f=await mount(view({materialPlan:plan}));
  const details=f.root.querySelector<HTMLDetailsElement>('details.new-task')!;
  const component=f.root.querySelector('domus-task-material-plan')!;await component.updateComplete;
  details.open=true;
  component.dispatchEvent(new CustomEvent('domus-material-plan-intent',{detail:{action:'load'},bubbles:true,composed:true}));
  f.element.view=view({phase:'loading',busy:true,access:null});await f.element.updateComplete;
  f.element.view=view({materialPlan:{...plan,open:true,notice:'unavailable'}});await f.element.updateComplete;
  expect(f.root.querySelector<HTMLDetailsElement>('details.new-task')!.open).toBe(true);
});

test.each(['en','es'] as const)('%s deferred material focus respects a newer keyboard target', async locale => {
  const choice={referenceId:'soap',name:'Soap',unit:'piece' as const};
  const plan={open:true,busy:false,canLink:true,readOnly:false,rows:[{referenceId:'soap',input:'4',choice}],choices:[choice],cursor:null,notice:null} as const;
  const f=await mount(view({materialPlan:plan}),locale);
  const component=f.root.querySelector('domus-task-material-plan')!;await component.updateComplete;
  const clear=component.shadowRoot!.querySelector<HaButton>('vyp-ha-button')!;await clear.updateComplete;clear.focus();
  const callbacks:FrameRequestCallback[]=[];
  const frames=vi.spyOn(window,'requestAnimationFrame').mockImplementation(callback=>{callbacks.push(callback);return callbacks.length;});
  try {
    clear.click();expect(f.intents.at(-1)).toEqual({type:'materialPlan',action:'clear'});
    f.element.view=view({materialPlan:{...plan,open:false,rows:[]}});
    await f.element.updateComplete;await component.updateComplete;await Promise.resolve();
    expect(callbacks.length).toBeGreaterThan(0);
    const refresh=f.button(locale==='en'?'Refresh tasks':'Actualizar tareas');refresh.focus();
    for(const callback of callbacks.splice(0))callback(performance.now());
    expect(f.root.activeElement).toBe(refresh);
    expect(f.intents).toEqual([{type:'materialPlan',action:'clear'}]);
  } finally {frames.mockRestore();}
});

test.each(['en','es'] as const)('%s clearing or removing the last denied material returns focus to the retained task title', async locale => {
  for(const action of ['clear','remove'] as const){
    const plan={open:true,busy:false,canLink:false,readOnly:false,notice:'forbidden',
      rows:[{referenceId:'soap',input:'4',choice:null}],choices:[],cursor:null} as const;
    const f=await mount(view({materialPlan:plan}),locale);
    f.root.querySelector<HTMLElement>('details.new-task summary')!.click();
    await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));await f.element.updateComplete;
    await f.input('task-title','Keep this title without materials');
    const component=f.root.querySelector('domus-task-material-plan')!;await component.updateComplete;
    const control=[...component.shadowRoot!.querySelectorAll<HaButton>('vyp-ha-button')]
      .find(button=>button.state.label===materialMessage(action,locale))!;
    await control.updateComplete;control.focus();control.click();
    expect(f.intents.at(-1)).toMatchObject({type:'materialPlan',action});
    f.element.view=view({materialPlan:{...plan,open:false,rows:[],notice:null}});
    await f.element.updateComplete;await component.updateComplete;
    await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
    const title=f.root.querySelector<HTMLInputElement>('#task-title')!;
    expect(f.root.activeElement).toBe(title);expect(title.value).toBe('Keep this title without materials');
    expect(f.button(locale==='en'?'Create task':'Crear tarea').disabled).toBe(false);
  }
});

test('missing material drafts survive a granular rejection and per-line success has a material-specific receipt', async () => {
  const material={intentId:'intent-1',cycleId:'cycle-1',lineId:'line-1',revision:revisionValue('7'),effectRevision:'1',submittedQuantity:null,
    quantity:null,state:'pending_recording' as const,pendingReason:'actual_quantity_required',confirmedQuantity:null,confirmedEffectRevision:null,movementId:null,postedAt:null};
  const detail:TaskDetail={...work,state:'completed',currentCycleId:'cycle-1',
    cycle:{cycleId:'cycle-1',verification:'pending',performedAt:'100',performerIds:['private-member-id']},
    materials:[{lineId:'line-1',label:'Soap',plannedQuantity:'2',precision:0,unitId:'piece',locationId:'pantry'}],materialOutcomes:[material],
    pendingMaterials:true,allowedActions:['materials.settle']};
  const f=await mount(view({detail}));
  const component=()=>f.root.querySelector('domus-task-material-outcomes')!;
  await component().updateComplete;
  const fields=()=>[...component().shadowRoot!.querySelectorAll<HaTextField>('vyp-ha-field')];
  fields()[0].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'0'}}));
  await f.element.updateComplete; await component().updateComplete;
  fields()[1].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'Nothing used'}}));
  await f.element.updateComplete; await component().updateComplete;
  let save=component().shadowRoot!.querySelector<HaButton>('vyp-ha-button')!; await save.updateComplete; save.click();
  expect(f.intents.at(-1)).toEqual({type:'settleMaterial',occurrenceId:'work-1',intentId:'intent-1',cycleId:'cycle-1',revision:'7',quantity:'0',reason:'Nothing used'});
  f.element.view=view({phase:'loading',busy:true,access:null,detail:null}); await f.element.updateComplete;
  f.element.view=view({detail,outcome:{kind:'rejected',reason:'forbidden',correlationId:'cor_material'}}); await f.element.updateComplete; await component().updateComplete;
  expect(fields().map(field=>field.value)).toEqual(['0','Nothing used']);
  await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
  save=component().shadowRoot!.querySelector<HaButton>('vyp-ha-button')!; await save.updateComplete; save.click();
  f.element.view=view({detail:null,notice:'unavailable'}); await f.element.updateComplete;
  const unused={...material,revision:revisionValue('8'),quantity:'0',state:'not_used' as const,pendingReason:null};
  const receipt:TaskReceipt={kind:'receipt',stage:'committed',action:'task.material.settle',operationId:'material-op',occurrenceId:work.occurrenceId,
    intentId:'intent-1',cycle:detail.cycle!,material:unused,archivedBy:null};
  f.element.view=view({detail:{...detail,materialOutcomes:[unused],pendingMaterials:false},outcome:receipt}); await f.element.updateComplete;
  await component().updateComplete; await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
  expect(f.text()).toContain('Material request recorded.'); expect(f.root.querySelector('#task-base-points')).toBeNull();
});

async function progressFixture(locale: 'en' | 'es' = 'en', patch: Partial<TaskDetail> = {}) {
  const detail: TaskDetail = {...work, state: 'assigned', assigneeIds: ['private-member-id'],
    allowedActions: ['transition:in_progress', 'transition:blocked', 'complete'], ...patch};
  const f = await mount(view({detail}), locale);
  const button = async (label: string) => {
    const found = [...f.root.querySelectorAll<HaButton>('vyp-ha-button')].find(item => item.state.label === label);
    if (!found) throw new Error('Missing progress control ' + label);
    await found.updateComplete;
    return found;
  };
  const settle = async () => {
    await f.element.updateComplete;
    await Promise.all([...f.root.querySelectorAll<HaButton>('vyp-ha-button')].map(item => item.updateComplete));
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  };
  const press = async (label: string) => {(await button(label)).click(); await settle();};
  return {...f, detail, progressButton: button, press, settle};
}

test.each([
  ['en', 'Block task', 'Save progress', 'Cancel', 'Task progress saved'],
  ['es', 'Bloquear tarea', 'Guardar progreso', 'Cancelar', 'Progreso de la tarea guardado'],
] as const)('%s progress retains its exact reason and supports cancel, save and confirmation', async (locale, block, save, cancel, confirmed) => {
  const f = await progressFixture(locale);
  await f.press(block);
  const reason = f.root.querySelector<HTMLTextAreaElement>('#task-progress-reason')!;
  expect(f.root.activeElement).toBe(reason);
  expect((await f.progressButton(save)).disabled).toBe(true);
  await f.input('task-progress-reason', 'Waiting for <parts>\n🧰');
  expect((await f.progressButton(save)).disabled).toBe(false);
  await f.press(cancel);
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.root.activeElement).toBe(await f.progressButton(block));
  expect(f.intents).toEqual([]);
  await f.press(block);
  await f.input('task-progress-reason', 'Waiting for <parts>\n🧰');
  await f.press(save);
  expect(f.intents).toEqual([{type: 'transition', occurrenceId: 'work-1', revision,
    target: 'blocked', reason: 'Waiting for <parts>\n🧰'}]);
  f.element.view = view({phase: 'loading', busy: true});
  await f.element.updateComplete;
  const saved: TaskReceipt = {kind: 'receipt', stage: 'committed', action: 'task.transition',
    occurrenceId: 'work-1', operationId: 'progress-op', revision: revisionValue('2'),
    state: 'blocked', stateReason: 'Waiting for <parts>\n🧰', cycle: null, archivedBy: null};
  f.element.view = view({detail: {...f.detail, state: 'blocked', revision: revisionValue('2'),
    stateReason: saved.stateReason, allowedActions: ['transition:assigned']}, outcome: saved});
  await f.element.updateComplete;
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.root.querySelector<HaFeedback>('#task-progress-result')?.state?.title).toBe(confirmed);
  expect(f.root.querySelector('#task-blocked-reason')?.textContent).toBe(saved.stateReason);
  expect(f.root.querySelector('img,script')).toBeNull();
});

test.each([
  {state: 'assigned', assigneeIds: ['private-member-id'], target: 'in_progress', label: 'Start task'},
  {state: 'blocked', assigneeIds: ['private-member-id'], target: 'assigned', label: 'Unblock task'},
  {state: 'blocked', assigneeIds: [], target: 'available', label: 'Unblock task'},
] as const)('$label confirms its $target target before emitting an exact progress command', async ({state, assigneeIds, target, label}) => {
  const f = await progressFixture('en', {state, assigneeIds, stateReason: state === 'blocked' ? 'Waiting' : '',
    allowedActions: ['transition:' + target]});
  await f.press(label);
  expect(f.intents).toEqual([]);
  expect(f.root.querySelector('#task-progress-reason')).toBeNull();
  expect(f.root.querySelector('#task-progress-version')?.textContent).toContain('1');
  await f.press('Save progress');
  expect(f.intents).toEqual([{type: 'transition', occurrenceId: 'work-1', revision, target, reason: ''}]);
});

test('progress validates meaningful text and Unicode bounds before any intent', async () => {
  const f = await progressFixture();
  await f.press('Block task');
  const form = f.root.querySelector<HTMLFormElement>('#task-progress-editor')!;
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  await f.settle();
  expect(f.intents).toEqual([]);
  expect(f.root.activeElement).toBe(f.root.querySelector('#task-progress-reason'));
  expect(f.root.querySelector('[role="alert"]')?.textContent).toContain('Enter a valid reason');
  for (const reason of [' \n\t', 'A\u0000B', '\ud800', '🧰'.repeat(1001)]) {
    await f.input('task-progress-reason', reason);
    expect((await f.progressButton('Save progress')).disabled).toBe(true);
    form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
    expect(f.intents).toEqual([]);
  }
  await f.input('task-progress-reason', '🧰'.repeat(1000));
  expect((await f.progressButton('Save progress')).disabled).toBe(false);
  await f.press('Save progress');
  expect(f.intents[0]).toMatchObject({target: 'blocked', reason: '🧰'.repeat(1000)});
});

test('a competing progress change retains the reason and requires separate review and save', async () => {
  const f = await progressFixture();
  await f.press('Block task');
  await f.input('task-progress-reason', 'My retained reason');
  await f.press('Save progress');
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2'), assigneeIds: ['peer']},
    outcome: {kind: 'rejected', reason: 'conflict', correlationId: 'safe-conflict'}});
  await f.element.updateComplete;
  expect((f.root.querySelector('#task-progress-reason') as HTMLTextAreaElement).value).toBe('My retained reason');
  expect((await f.progressButton('Save progress')).disabled).toBe(true);
  expect(f.intents).toHaveLength(1);
  await f.press('Review current task');
  expect(f.root.activeElement).toBe(await f.progressButton('Save progress'));
  expect((await f.progressButton('Save progress')).disabled).toBe(false);
  expect(f.intents).toHaveLength(1);
  await f.press('Save progress');
  expect(f.intents[1]).toEqual({type: 'transition', occurrenceId: 'work-1', revision: '2',
    target: 'blocked', reason: 'My retained reason'});
});

test('an unavailable progress target retains the proposal and offers refresh or cancellation', async () => {
  const f = await progressFixture();
  await f.press('Block task');
  await f.input('task-progress-reason', 'My retained reason');
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2'), state: 'blocked',
    stateReason: 'The other member blocked it', allowedActions: ['transition:assigned']}});
  await f.element.updateComplete;
  expect((await f.progressButton('Save progress')).disabled).toBe(true);
  expect(f.root.querySelector<HaFeedback>('#task-progress-unavailable')?.state?.message).toContain('This action is unavailable');
  expect((f.root.querySelector('#task-progress-reason') as HTMLTextAreaElement).value).toBe('My retained reason');
  await f.press('Refresh current task');
  expect(f.intents).toEqual([{type: 'refresh'}]);
  await f.press('Cancel');
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.root.querySelector('#task-blocked-reason')?.textContent).toBe('The other member blocked it');
});

test('recoverable loading preserves a progress draft while scope retirement clears it', async () => {
  const f = await progressFixture();
  await f.press('Block task');
  await f.input('task-progress-reason', 'A retained explanation');
  f.element.view = view({phase: 'loading', busy: true});
  await f.element.updateComplete;
  f.element.view = view({detail: f.detail, notice: 'unavailable'});
  await f.element.updateComplete;
  expect((f.root.querySelector('#task-progress-reason') as HTMLTextAreaElement).value).toBe('A retained explanation');
  f.element.view = view({detail: f.detail, scopeKey: 'different-household'});
  await f.element.updateComplete;
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.intents).toEqual([]);
});

test.each([
  {state: 'available', assigneeIds: [], allowedActions: ['transition:in_progress']},
  {state: 'assigned', assigneeIds: ['private-member-id'], allowedActions: []},
  {state: 'blocked', assigneeIds: ['private-member-id'], allowedActions: ['transition:available']},
  {state: 'completed', assigneeIds: ['private-member-id'], allowedActions: ['transition:blocked']},
] as const)('progress state and matching hint are both required %#', async patch => {
  const f = await progressFixture('en', {...patch, stateReason: 'Saved explanation'});
  expect(f.root.querySelectorAll('#task-progress-actions vyp-ha-button')).toHaveLength(0);
});

test('read-only access disables offered progress controls', async () => {
  const f = await progressFixture();
  f.element.view = view({detail: f.detail, readOnly: true});
  await f.element.updateComplete;
  expect((await f.progressButton('Start task')).disabled).toBe(true);
  expect((await f.progressButton('Block task')).disabled).toBe(true);
  await f.press('Block task');
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.intents).toEqual([]);
});

test('a blocking reason remains readable and inert without mutation authority', async () => {
  const reason = 'Waiting for <img src=x onerror=alert(1)>\n🧰';
  const f = await progressFixture('en', {state: 'blocked', stateReason: reason, allowedActions: []});
  expect(f.root.querySelector('#task-blocked-reason')?.textContent).toBe(reason);
  expect(f.root.querySelector('img,script')).toBeNull();
});

test('only the matching submitted progress receipt closes the editor at int64 precision', async () => {
  const captured = revisionValue('9223372036854775806');
  const next = revisionValue('9223372036854775807');
  const f = await progressFixture('en', {revision: captured});
  await f.press('Block task');
  await f.input('task-progress-reason', 'Waiting');
  await f.press('Save progress');
  const saved: TaskReceipt = {kind: 'receipt', stage: 'committed', action: 'task.transition', operationId: 'progress-op',
    occurrenceId: 'work-1', revision: next, state: 'blocked', stateReason: 'Waiting', cycle: null, archivedBy: null};
  for (const patch of [
    {stage: 'historical', archivedBy: 'restore-op'},
    {occurrenceId: 'different-task'},
    {revision: captured},
    {state: 'in_progress'},
    {stateReason: 'Different reason'},
  ] satisfies Partial<TaskReceipt>[]) {
    f.element.view = view({detail: f.detail, outcome: {...saved, ...patch}});
    await f.element.updateComplete;
    expect(f.root.querySelector('#task-progress-editor')).not.toBeNull();
  }
  f.element.view = view({detail: {...f.detail, revision: next, state: 'blocked', stateReason: 'Waiting', allowedActions: []}, outcome: saved});
  await f.element.updateComplete;
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
});


test('a same-revision server conflict needs one explicit review and a separate save', async () => {
  const f = await progressFixture();
  await f.press('Start task'); await f.press('Save progress');
  const conflict = {kind: 'rejected', reason: 'conflict', correlationId: 'safe-conflict'} as const;
  f.element.view = view({detail: f.detail, outcome: conflict}); await f.settle();
  expect((await f.progressButton('Save progress')).disabled).toBe(true);
  expect(f.root.activeElement).toBe(await f.progressButton('Review current task'));
  f.element.view = view({detail: f.detail, outcome: conflict}); await f.settle();
  await f.press('Review current task');
  expect(f.intents).toHaveLength(1);
  expect((await f.progressButton('Save progress')).disabled).toBe(false);
  await f.press('Save progress'); expect(f.intents).toHaveLength(2);
});

test('reviewing a changed blank blocking draft returns focus to its required reason', async () => {
  const f = await progressFixture();
  await f.press('Block task');
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2')}}); await f.settle();
  await f.press('Review current task');
  expect(f.root.activeElement).toBe(f.root.querySelector('#task-progress-reason'));
  expect((await f.progressButton('Save progress')).disabled).toBe(true);
  expect(f.intents).toEqual([]);
});

test('start confirmation survives unavailable reads and task selection retires its proposal', async () => {
  const f = await progressFixture();
  await f.press('Start task');
  f.element.view = view({phase: 'loading', busy: true}); await f.settle();
  f.element.view = view({detail: f.detail, notice: 'unavailable'}); await f.settle();
  expect(f.root.activeElement).toBe(await f.progressButton('Save progress'));
  f.element.view = view({detail: {...f.detail, occurrenceId: 'different-task'}}); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  expect(f.intents).toEqual([]);
});

test('progress event handlers reject retired controls and state changes before rendering', async () => {
  const f = await progressFixture();
  const trigger = await f.progressButton('Block task');
  const press = (control: Element) => control.dispatchEvent(new CustomEvent('ha-press-request'));
  f.element.view = view({detail: null}); press(trigger); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  f.element.view = view({detail: f.detail}); await f.settle();
  const current = await f.progressButton('Block task');
  f.element.view = view({detail: f.detail, readOnly: true}); press(current); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  f.element.view = view({detail: f.detail}); await f.settle();
  const unavailable = await f.progressButton('Block task');
  f.element.view = view({detail: {...f.detail, allowedActions: []}}); press(unavailable); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  f.element.view = view({detail: f.detail}); await f.settle();
  await f.press('Block task'); await f.input('task-progress-reason', 'Keep this draft');
  const form = f.root.querySelector<HTMLFormElement>('#task-progress-editor')!;
  const reason = f.root.querySelector<HTMLTextAreaElement>('#task-progress-reason')!;
  const submit = () => form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  f.element.view = view({detail: f.detail, readOnly: true});
  reason.value = 'Ignore this stale input'; reason.dispatchEvent(new InputEvent('input')); submit(); await f.settle();
  f.element.view = view({detail: f.detail}); await f.settle();
  expect(reason.value).toBe('Keep this draft');
  f.element.view = view({detail: null}); submit(); await f.settle();
  f.element.view = view({detail: f.detail}); await f.settle();
  f.element.view = view({detail: {...f.detail, occurrenceId: 'another-task'}}); submit(); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
  submit(); reason.dispatchEvent(new InputEvent('input')); await f.settle();
  expect(f.intents).toEqual([]);
});

test('a target revoked at the same revision cannot be submitted or reviewed by a stale control', async () => {
  const f = await progressFixture();
  await f.press('Block task'); await f.input('task-progress-reason', 'Waiting');
  const form = f.root.querySelector<HTMLFormElement>('#task-progress-editor')!;
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2')}}); await f.settle();
  const review = await f.progressButton('Review current task');
  const press = () => review.dispatchEvent(new CustomEvent('ha-press-request'));
  f.element.view = view({detail: null}); press();
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2')}, readOnly: true}); press();
  f.element.view = view({detail: {...f.detail, occurrenceId: 'other-task'}}); press();
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2'), allowedActions: []}}); press(); await f.settle();
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); await f.settle();
  expect(f.root.activeElement).toBe(form);
  f.element.view = view({detail: {...f.detail, allowedActions: []}}); await f.settle();
  form.dispatchEvent(new SubmitEvent('submit', {cancelable: true})); await f.settle();
  expect(f.intents).toEqual([]);
  await f.press('Cancel'); press(); await f.settle();
  expect(f.root.querySelector('#task-progress-editor')).toBeNull();
});

test('a pending focus survives a temporarily absent detail without focusing detached controls', async () => {
  const f = await progressFixture();
  const trigger = await f.progressButton('Start task');
  trigger.dispatchEvent(new CustomEvent('ha-press-request'));
  f.element.view = view({detail: null}); await f.settle();
  f.element.view = view({detail: f.detail}); await f.settle();
  expect(f.root.activeElement).toBe(await f.progressButton('Save progress'));
  (await f.progressButton('Cancel')).dispatchEvent(new CustomEvent('ha-press-request'));
  await f.element.updateComplete;
  f.element.remove(); await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  expect(f.intents).toEqual([]);
});

test('a blocked legacy detail has a readable missing-reason fallback', async () => {
  const f = await progressFixture('en', {state: 'blocked', stateReason: undefined, allowedActions: []});
  expect(f.root.querySelector('#task-blocked-reason')?.textContent).toBe('The blocking reason is unavailable.');
});

function assignmentRoster(): Pick<AdministrationView, 'phase' | 'access' | 'roster' | 'errors'> {
  const member = {memberId: 'private-member-id', haUserId: context.subject, role: 'adult' as const,
    status: 'active' as const, revision, exceptions: []};
  return {phase: 'ready', access: {state: 'active', setupAllowed: false, enrollmentAllowed: false,
    member, effectiveRole: 'adult', policyRevision: revision, permissions: ['members.read']}, errors: {},
    roster: {directoryState: 'available', members: ['private-member-id', 'peer'].map((id, index) => ({
      member: {...member, memberId: id}, presentation: {memberId: id, alias: index === 0 ? 'Owner <name>' : null, revision},
      metadata: {state: 'available', name: index === 0 ? 'Provider owner' : 'Helper & friend', avatarState: 'unavailable'}}))}};
}
async function assignmentFixture(locale: 'en' | 'es' = 'en', patch: Partial<TaskDetail> = {}) {
  const detail = {...work, allowedActions: ['assign'], ...patch};
  const f = await mount(view({detail}), locale);
  f.element.administration = assignmentRoster(); await f.element.updateComplete;
  const select = async (index: number, checked: boolean) => {
    const choice = f.root.querySelectorAll<HaCheckbox>('vyp-ha-checkbox')[index];
    await choice.updateComplete;
    choice.dispatchEvent(new CustomEvent('ha-check-request', {detail: {checked, reason: 'change'}, bubbles: true, composed: true, cancelable: true}));
    await f.element.updateComplete;
  };
  return {...f, detail, select};
}

test('progress confirmation preserves an assignment draft while hiding its competing action', async () => {
  const f = await assignmentFixture('en', {allowedActions: ['assign', 'transition:blocked', 'complete']});
  f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true);
  const editor = f.root.querySelector('#assignment-editor');
  const trigger = f.root.querySelector<HaButton>('#task-progress-blocked')!;
  await trigger.updateComplete; trigger.click(); await f.element.updateComplete;
  expect(f.root.querySelector('.task-work-actions')?.hasAttribute('hidden')).toBe(true);
  expect(f.root.querySelector('#assignment-editor')).toBe(editor);
  const cancel = [...f.root.querySelectorAll<HaButton>('vyp-ha-button')].find(button => button.state.label === 'Cancel')!;
  await cancel.updateComplete; cancel.click(); await f.element.updateComplete;
  expect(f.root.querySelector('.task-work-actions')?.hasAttribute('hidden')).toBe(false);
  expect(f.root.querySelector<HaCheckbox>('vyp-ha-checkbox')?.checked).toBe(true);
  expect(f.intents).toEqual([]);
});

test.each([
  ['en', []], ['es', []],
  ['en', ['peer']], ['es', ['peer']],
  ['en', ['private-member-id', 'peer']], ['es', ['private-member-id', 'peer']],
] as const)('%s unchanged assignment %j requires a different selection before saving', async (locale, assigneeIds) => {
  const f = await assignmentFixture(locale, {assigneeIds, state: assigneeIds.length ? 'assigned' : 'available'});
  const edit = locale === 'en' ? 'Change assignment' : 'Cambiar asignación';
  const save = locale === 'en' ? 'Save assignment' : 'Guardar asignación';
  f.button(edit).click(); await f.element.updateComplete;
  expect(f.button(save).disabled).toBe(true);
  expect(f.text()).toContain(locale === 'en' ? 'Choose a different assignment to save a change.'
    : 'Elige una asignación diferente para guardar un cambio.');
  f.root.querySelector('#assignment-editor')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]);
  const selected = assigneeIds.some(id => id === 'private-member-id');
  await f.select(0, !selected); expect(f.button(save).disabled).toBe(false);
  await f.select(0, selected); expect(f.button(save).disabled).toBe(true);
  expect(f.intents).toEqual([]);
});

test('reviewing a competing assignment equal to the retained selection requires a new change', async () => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true);
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2'), assigneeIds: ['private-member-id'], state: 'assigned'}});
  await f.element.updateComplete;
  f.button('Review current assignment').click(); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(true);
  f.root.querySelector('#assignment-editor')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]);
});

test.each([
  ['en', 'Change assignment', 'Save assignment', 'Cancel', 'Unassigned'],
  ['es', 'Cambiar asignación', 'Guardar asignación', 'Cancelar', 'Sin asignar'],
] as const)('%s assignment uses named ha-ui choices and explicit save or cancel', async (locale, edit, save, cancel, unassigned) => {
  const f = await assignmentFixture(locale);
  expect(f.text()).toContain(unassigned);
  f.button(edit).click(); await f.element.updateComplete;
  const choices = f.root.querySelectorAll<HaCheckbox>('vyp-ha-checkbox');
  await choices[0].updateComplete;
  expect(choices[0].state.label).toBe('Owner <name>');
  expect(choices[1].state.label).toBe('Helper & friend');
  expect(f.root.querySelector('img,script')).toBeNull();
  expect(f.root.activeElement).toBe(choices[0]);
  await f.select(0, true); await f.select(1, true);
  f.button(save).click();
  expect(f.intents).toEqual([{type: 'assign', occurrenceId: 'work-1', revision, assigneeIds: ['private-member-id', 'peer']}]);
  f.element.view = view({phase: 'loading', busy: true}); await f.element.updateComplete;
  f.element.view = view({detail: f.detail, notice: 'unavailable'}); await f.element.updateComplete;
  expect([...f.root.querySelectorAll<HaCheckbox>('vyp-ha-checkbox')].map(choice => choice.checked)).toEqual([true, true]);
  f.button(cancel).click(); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
  expect(f.root.activeElement).toBe(f.button(edit));
  f.button(edit).click(); await f.element.updateComplete;
  expect([...f.root.querySelectorAll<HaCheckbox>('vyp-ha-checkbox')].map(choice => choice.checked)).toEqual([false, false]);
});

test('assignment conflict retains the draft and requires review of the current revision before another save', async () => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true); f.button('Save assignment').click();
  const changed = {...f.detail, revision: revisionValue('2'), assigneeIds: ['peer']};
  f.element.view = view({detail: changed, notice: 'conflict'}); await f.element.updateComplete;
  expect(f.root.querySelector<HaCheckbox>('vyp-ha-checkbox')!.checked).toBe(true);
  expect(f.button('Save assignment').disabled).toBe(true);
  expect(f.root.activeElement).toBe(f.button('Review current assignment'));
  f.button('Review current assignment').click(); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(false);
  f.button('Save assignment').click();
  expect(f.intents[1]).toEqual({type: 'assign', occurrenceId: 'work-1', revision: '2', assigneeIds: ['private-member-id']});
  f.element.view = view({detail: {...changed, revision: revisionValue('3'), assigneeIds: ['private-member-id']}, outcome: {
    kind: 'receipt', action: 'task.assign', stage: 'committed', operationId: 'assignment-op', occurrenceId: 'work-1',
    revision: revisionValue('3'), state: 'assigned', assigneeIds: ['private-member-id'], cycle: null, archivedBy: null}});
  await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
  expect(f.text()).toContain('Assignment saved');
});

test('assignment release follows the current task state and stale members require correction', async () => {
  const f = await assignmentFixture('en', {assigneeIds: ['peer']});
  f.button('Change assignment').click(); await f.element.updateComplete;
  f.button('Clear selection').click(); await f.element.updateComplete;
  f.button('Save assignment').click();
  expect(f.intents[0]).toMatchObject({type: 'assign', assigneeIds: []});
  f.element.view = view({detail: {...f.detail, state: 'in_progress'}}); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(true);
  expect(f.text()).toContain('An in-progress task needs at least one assignee.');
  await f.select(0, true);
  const roster = assignmentRoster();
  f.element.administration = {...roster, roster: {...roster.roster!, members: roster.roster!.members.slice(1)}};
  await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(true);
  expect(f.text()).toContain('Remove unavailable members or refresh the choices.');
  f.button('Remove unavailable member').click(); await f.element.updateComplete;
  expect(f.root.querySelector('[data-stale-assignee]')).toBeNull();
});

test.each(['loading', 'empty', 'unavailable', 'denied', 'permission', 'missing'] as const)(
  'assignment discovery %s has distinct feedback and preserves a recoverable selection', async state => {
    const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
    await f.select(0, true);
    const roster = assignmentRoster();
    f.element.administration = state === 'missing' ? null : {...roster,
      ...state === 'loading' ? {phase: 'loading' as const, roster: null} : {},
      ...state === 'empty' ? {roster: {...roster.roster!, members: []}} : {},
      ...state === 'unavailable' ? {roster: null, errors: {roster: 'unavailable' as const}} : {},
      ...state === 'denied' ? {roster: null, errors: {roster: 'forbidden' as const}} : {},
      ...state === 'permission' ? {roster: null, access: {...roster.access!, permissions: []}} : {}};
    await f.element.updateComplete;
    const expected = state === 'loading' || state === 'missing' ? 'Loading household members'
      : state === 'empty' ? 'No active household members are available.' : state === 'unavailable'
        ? 'Household members could not be loaded.' : 'Your current access does not allow viewing household members.';
    expect(f.text()).toContain(expected);
    expect(f.button('Save assignment').disabled).toBe(true);
    f.button('Refresh assignment and members').click();
    expect(f.intents).toEqual([{type: 'refresh'}]);
    f.element.administration = roster; await f.element.updateComplete;
    expect(f.root.querySelector<HaCheckbox>('vyp-ha-checkbox')!.checked).toBe(true);
  });

test('assignment controls follow current actions and scoped retirement clears their draft', async () => {
  const ordinary = await mount(view({detail: work}));
  expect(ordinary.button('Change assignment')).toBeUndefined();
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true);
  f.element.view = view({detail: f.detail, scopeKey: 'different-household'}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
  f.button('Change assignment').click(); await f.element.updateComplete;
  f.element.retired = true; await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
});

test('assignment choices retain canonical IDs when provider names are unavailable and enforce the 32-member bound', async () => {
  const f = await assignmentFixture(); const roster = assignmentRoster(), member = roster.roster!.members[0];
  f.element.administration = {...roster, roster: {directoryState: 'denied', members: Array.from({length: 33}, (_, index) => ({
    ...member, member: {...member.member, memberId: 'member-' + index},
    presentation: {...member.presentation, memberId: 'member-' + index, alias: null},
    metadata: {...member.metadata, state: 'denied', name: null}}))}};
  await f.element.updateComplete;
  f.button('Change assignment').click(); await f.element.updateComplete;
  for (let index = 0; index < 32; index++) await f.select(index, true);
  const choices = f.root.querySelectorAll<HaCheckbox>('vyp-ha-checkbox');
  expect(choices[0].state.label).toBe('Household member member-0');
  expect(choices[32].disabled).toBe(true); expect(choices[0].disabled).toBe(false);
  await f.select(32, true);
  expect(f.text()).toContain('Choose up to 32 different household members.');
  f.button('Save assignment').click();
  expect(f.intents[0]).toMatchObject({type: 'assign', assigneeIds: Array.from({length: 32}, (_, index) => 'member-' + index)});
  await f.select(0, false); await f.select(32, true);
  expect(f.text()).not.toContain('Choose up to 32 different household members.');
  f.element.view = view({detail: f.detail, records: [{key: 'pending', command: {action: 'task.assign', occurrenceId: 'work-1',
    payload: {expected_revision: revision, assignee_ids: ['member-1']}}, scope: {context, householdId: 'private-home-id', memberId: 'private-member-id'},
    createdAt: 1000, expiresAt: 3601000, stage: 'uncertain', operationId: null}]});
  await f.element.updateComplete;
  await f.select(1, false); f.button('Save assignment').click();
  f.root.querySelector('#assignment-editor')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toHaveLength(1);
});

test('assignment editor retires on another task or revoked action and guards uncertain or stale submits', async () => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2')}}); await f.element.updateComplete;
  f.root.querySelector('#assignment-editor')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]);
  f.button('Review current assignment').click(); await f.element.updateComplete;
  f.element.view = view({detail: {...f.detail, occurrenceId: 'other-work'}}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
  f.button('Change assignment').click(); await f.element.updateComplete;
  f.element.view = view({detail: {...f.detail, occurrenceId: 'other-work', allowedActions: []}}); await f.element.updateComplete;
  expect(f.root.querySelector('#assignment-editor')).toBeNull();
  expect(f.button('Change assignment')).toBeUndefined();
});

test('assignment focus survives a pending refresh and opens an unavailable roster at the editor', async () => {
  const f = await assignmentFixture();
  f.button('Change assignment').click();
  f.element.view = view({phase: 'loading', busy: true}); await f.element.updateComplete;
  expect(f.root.querySelector('#assignment-editor')).toBeNull();
  f.element.administration = null;
  f.element.view = view({detail: f.detail}); await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('assignment-editor');
  f.root.querySelector('#assignment-editor')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  expect(f.intents).toEqual([]);
  f.button('Cancel').click(); await f.element.updateComplete;
  f.element.administration = assignmentRoster(); await f.element.updateComplete;
  f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true);
  f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, notice: 'invalid_input'}); await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('assignment-editor');
  f.button('Clear selection').click(); await f.element.updateComplete;
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2'), state: 'in_progress'}}); await f.element.updateComplete;
  f.button('Review current assignment').click(); await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('assignment-editor');
  expect(f.button('Save assignment').disabled).toBe(true);
});

test('a retained older assignment receipt cannot close a newer submitted editor', async () => {
  const receipt = {kind: 'receipt' as const, stage: 'committed' as const, action: 'task.assign' as const,
    occurrenceId: 'work-1', operationId: 'older-op', revision: revisionValue('2'), state: 'assigned' as const,
    cycle: null, archivedBy: null, assigneeIds: ['peer']};
  const f = await assignmentFixture('en', {revision: revisionValue('2'), assigneeIds: ['peer']});
  f.element.view = view({detail: f.detail, outcome: receipt}); await f.element.updateComplete;
  f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true); f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, outcome: receipt}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).not.toBeNull();
  f.element.view = view({detail: f.detail, outcome: {...receipt, assigneeIds: undefined}}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).not.toBeNull();
  const matchingIds = ['peer', 'private-member-id'];
  f.element.view = view({detail: f.detail, outcome: {...receipt, assigneeIds: matchingIds}}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).not.toBeNull();
  const alreadyRead = {...receipt, revision: revisionValue('3'), assigneeIds: matchingIds};
  f.element.view = view({detail: f.detail, outcome: alreadyRead});
  await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).toBeNull();
  f.button('Change assignment').click(); await f.element.updateComplete;
  f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, outcome: alreadyRead}); await f.element.updateComplete;
  expect(f.root.querySelector('vyp-ha-checkbox')).not.toBeNull();
});

test('a rejected assignment keeps the draft and an unresolved conflict requires deliberate review', async () => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true); f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, outcome: {kind: 'rejected', reason: 'invalid_input', correlationId: 'safe-invalid'}});
  await f.element.updateComplete;
  expect(f.root.querySelector<HaCheckbox>('vyp-ha-checkbox')!.checked).toBe(true);
  expect(f.button('Review current assignment')).toBeUndefined();
  f.element.view = view({detail: f.detail, outcome: {kind: 'rejected', reason: 'conflict', correlationId: 'safe-conflict'}});
  await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(true);
  f.button('Review current assignment').click(); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(false);
});

test.each(['unavailable', 'invalid_response'] as const)('assignment conflict with a %s current read requires a refresh', async notice => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true); f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, notice, outcome: {kind: 'rejected', reason: 'conflict', correlationId: 'safe-conflict'}});
  await f.element.updateComplete;
  expect(f.button('Review current assignment').disabled).toBe(true);
  expect(f.button('Save assignment').disabled).toBe(true);
  f.button('Refresh assignment and members').click();
  expect(f.intents.at(-1)).toEqual({type: 'refresh'});
  f.element.view = view({detail: {...f.detail, revision: revisionValue('2')}}); await f.element.updateComplete;
  f.button('Review current assignment').click(); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(false);
});

test('an exhausted task revision retains the assignment editor when an earlier receipt is recovered', async () => {
  const last = revisionValue('9223372036854775807');
  const f = await assignmentFixture('en', {revision: last, assigneeIds: ['peer']});
  f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(0, true);
  f.button('Save assignment').click();
  f.element.view = view({detail: f.detail, outcome: {kind: 'receipt', action: 'task.assign', stage: 'committed',
    occurrenceId: 'work-1', operationId: 'last-operation', revision: last, state: 'assigned',
    assigneeIds: ['peer', 'private-member-id'], cycle: null, archivedBy: null}});
  await f.element.updateComplete;
  expect(f.root.querySelector('#assignment-editor')).not.toBeNull();
  expect(f.intents[0]).toMatchObject({type: 'assign', revision: last, assigneeIds: ['peer', 'private-member-id']});
});

test('a denied assignee retains the selection and offers removal after the authorized roster changes', async () => {
  const f = await assignmentFixture(); f.button('Change assignment').click(); await f.element.updateComplete;
  await f.select(1, true); f.button('Save assignment').click();
  const roster = assignmentRoster();
  f.element.administration = {...roster, roster: {...roster.roster!, members: roster.roster!.members.map(row =>
    row.member.memberId === 'peer' ? {...row, member: {...row.member, status: 'suspended'}} : row)}};
  f.element.view = view({detail: f.detail, outcome: {kind: 'rejected', reason: 'assignees_unavailable', correlationId: 'safe-member'}});
  await f.element.updateComplete;
  expect(f.text()).toContain('Some selected members are unavailable.');
  expect(f.root.querySelector('[data-stale-assignee]')!.textContent).toContain('Helper & friend');
  expect(f.button('Save assignment').disabled).toBe(true);
  f.button('Remove unavailable member').click(); await f.element.updateComplete;
  expect(f.button('Save assignment').disabled).toBe(true);
  await f.select(0, true);
  expect(f.button('Save assignment').disabled).toBe(false);
});
test('usable task creation preserves literal input and emits one semantic intent', async () => {
  const f = await mount(); expect(f.root.querySelector<HTMLSelectElement>('#task-priority')!.value).toBe('normal');
  await f.input('task-title', '  Clean 🧹  '); await f.input('task-description', 'Wipe then dry');
  f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {bubbles: true, cancelable: true}));
  expect(f.intents).toEqual([{type: 'create', title: '  Clean 🧹  ', description: 'Wipe then dry', priority: 'normal'}]);
  expect(f.text()).not.toContain('private-home-id'); expect(f.text()).not.toContain('private-member-id');
  expect(f.root.querySelector('#task-base-points')).toBeNull();
});
test.each([
  ['en', 'Base points (optional)', '2.25', 'Enter 0 to 10,000 points'],
  ['es', 'Puntos base (opcional)', '2,25', 'Introduce entre 0 y 10.000 puntos'],
] as const)('authorized %s form preserves the draft and submits exact base points', async (locale, label, value, error) => {
  const access = {...view().access!, canConfigure: true};
  const f = await mount(view({access}), locale);
  f.root.querySelector<HTMLDetailsElement>('details.new-task')!.open = true;
  const field = f.root.querySelector<HaTextField>('#task-base-points')!;
  await field.updateComplete;
  const amount = field.shadowRoot!.querySelector('input')!;
  expect(amount.getAttribute('aria-label')).toBe(label);
  const edit = async (text: string) => {
    amount.value = text;
    amount.dispatchEvent(new InputEvent('input', {bubbles: true}));
    await f.element.updateComplete;
    await field.updateComplete;
  };
  const submit = () => f.root.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  await f.input('task-title', 'Inspect filter');
  submit();
  expect(f.intents.pop()).toEqual({type: 'create', title: 'Inspect filter', description: '', priority: 'normal'});
  await edit('1,001');
  submit(); await f.element.updateComplete; await field.updateComplete;
  expect(field.value).toBe('1,001'); expect(field.shadowRoot!.textContent).toContain(error);
  expect(f.root.activeElement).toBe(field); expect(f.intents).toEqual([]);
  await edit(value); submit();
  expect(f.intents).toEqual([{type: 'create', title: 'Inspect filter', description: '', priority: 'normal', basePointsMinor: 225}]);
  f.element.view = view({access, outcome: {kind: 'rejected', reason: 'points_precision_two_required', correlationId: 'cor_precision'}});
  await f.element.updateComplete; await field.updateComplete;
  expect(field.shadowRoot!.textContent).toContain(locale === 'en' ? 'Use whole base points' : 'Usa puntos base enteros');
  expect(amount.getAttribute('aria-invalid')).toBe('true');
  expect(field.value).toBe(value);
  expect(f.root.activeElement).toBe(field);
  f.element.view = {...f.element.view!};
  await f.element.updateComplete; await field.updateComplete;
  expect(amount.getAttribute('aria-invalid')).toBe('true');
  await edit('2');
  expect(amount.getAttribute('aria-invalid')).not.toBe('true');
  await edit(value); submit();
  f.element.view = view({access, outcome: {kind: 'receipt', stage: 'committed', action: 'task.create',
    operationId: 'configured', occurrenceId: 'work-1', revision, state: 'available', cycle: null, archivedBy: null, basePointsMinor: 225}});
  await f.element.updateComplete; await field.updateComplete;
  expect(f.root.querySelector('section[role=status] dd')?.textContent).toBe(value);
  expect(field.value).toBe('');
});

test('revoking configuration in the same scope asks for explicit removal of the draft amount', async () => {
  const access = {...view().access!, canConfigure: true};
  const f = await mount(view({access}));
  await f.input('task-title', 'Keep the title');
  const field = f.root.querySelector<HaTextField>('#task-base-points')!;
  field.dispatchEvent(new CustomEvent('ha-value-request', {detail: {value: '0', reason: 'input'}}));
  await f.element.updateComplete;
  const form = f.root.querySelector('form')!;
  const submit = () => form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  submit(); expect(f.intents.pop()).toMatchObject({basePointsMinor: 0});
  f.element.view = view({access: {...access, canConfigure: false}});
  await f.element.updateComplete;
  expect(f.root.querySelector('#task-base-points')).toBeNull();
  expect(f.button('Create task').disabled).toBe(true); submit(); expect(f.intents).toEqual([]);
  f.button('Clear base points').click(); await f.element.updateComplete; submit();
  expect(f.intents).toEqual([{type: 'create', title: 'Keep the title', description: '', priority: 'normal'}]);
});
test.each([['en','fixed'],['es','relative']] as const)('scheduled task form in %s preserves invalid input and emits a %s draft', async (locale, kind) => {
  const access = {...view().access!, schedulePolicy: {zone: 'Europe/Madrid', data_identity: 'tzdata:2026.6/iana:2026f',
    repeated_time: 'first_instant' as const, revision}};
  const f = await mount(view({access}), locale);
  await f.input('task-title', 'Check the filter');
  const schedule = f.root.querySelector<HTMLSelectElement>('#task-schedule')!;
  schedule.value = kind; schedule.dispatchEvent(new Event('change')); await f.element.updateComplete;
  const form = f.root.querySelector('form')!;
  const submit = () => form.dispatchEvent(new SubmitEvent('submit', {cancelable: true}));
  submit(); await f.element.updateComplete;
  expect(f.root.querySelector('fieldset [role=alert]')).not.toBeNull();
  expect(f.intents).toEqual([]);
  const fill = (name: string, value: string) => {
    const input = form.querySelector<HTMLInputElement>(`[name="${name}"]`)!;
    input.value = value;
    input.dispatchEvent(new Event(name === 'schedule-visibility' ? 'change' : 'input', {bubbles:true}));
  };
  fill('schedule-date', '2027-01-02');
  if (kind === 'fixed') {fill('schedule-time', '08:30'); fill('schedule-rule', 'FREQ=WEEKLY');}
  else {fill('schedule-interval', '18'); fill('schedule-visibility', 'at_verification');}
  submit(); await f.element.updateComplete;
  const start = kind === 'fixed' ? {kind: 'time', local: '2027-01-02T08:30'} : {kind: 'date', local: '2027-01-02'};
  expect(f.intents).toEqual([{type: 'create', title: 'Check the filter', description: '', priority: 'normal',
    schedule: {kind, start, ...kind === 'fixed' ? {rrule: 'FREQ=WEEKLY'} : {interval_days: 18, visibility: 'at_verification'}}}]);
  f.element.view = view({access, outcome: {kind: 'receipt', stage: 'committed', action: 'task.create', operationId: 'scheduled',
    occurrenceId: null, revision, state: 'active', cycle: null, archivedBy: null}});
  await f.element.updateComplete;
  expect(schedule.value).toBe('manual');
  expect(f.text()).toContain(locale === 'en' ? 'The schedule was saved.' : 'Se ha guardado la programación.');
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
test('the task list and selected detail display the same date-only deadline in both locales', async () => {
  const dated = {...work, dueDate: '2026-04-02'};
  const f = await mount(view({page: {items: [dated], nextCursor: null}, detail: dated}));
  expect(f.root.querySelector('.task-meta')!.textContent).toContain('Apr 2, 2026');
  expect(f.text()).toContain('Due: Apr 2, 2026');
  expect(f.text()).not.toContain('No due date');
  f.element.language = 'es';
  await f.element.updateComplete;
  expect(f.root.querySelector('.task-meta')!.textContent).toContain('2 abr 2026');
  expect(f.text()).toContain('Vencimiento: 2 abr 2026');
  expect(f.text()).not.toContain('Sin fecha de vencimiento');
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

test('category management keeps exact revision and drafts across a stale catalog and authorized recovery', async () => {
  const category = {id:'garden', label:'<b>Garden</b>', revision};
  const access = view().access!;
  const editable = {...access, categoryCatalog:{canManage:true, categories:[category]}};
  const state = (patch: Partial<TaskView> = {}) => view({access:editable, ...patch});
  const f = await mount(state({detail:{...work, categoryLabel:category.label}}));
  expect(f.text()).toContain(category.label);
  expect(f.root.querySelector('b')).toBeNull();
  const choose = (id: string, value: string) => {
    const select = f.root.querySelector<HTMLSelectElement>('#' + id)!;
    select.value = value;
    select.dispatchEvent(new Event('change', {bubbles:true}));
  };
  const submit = (form: HTMLFormElement) => form.dispatchEvent(new SubmitEvent('submit',{cancelable:true}));
  const manager = f.root.querySelector<HTMLSelectElement>('#manage-task-category')!.closest('form')!;
  const details = manager.closest('details')!;
  details.open = true;
  details.dispatchEvent(new Event('toggle'));
  expect(f.button('Create category').disabled).toBe(true);
  submit(manager);
  expect(f.intents).toEqual([]);
  await f.input('task-category-label', 'bad\u007f');
  expect(f.root.querySelector('#task-category-label')?.getAttribute('aria-invalid')).toBe('true');
  await f.input('task-category-label', 'A new category');
  submit(manager);
  expect(f.intents.at(-1)).toEqual({type:'createCategory', label:'A new category'});
  const saved = {kind:'receipt' as const, stage:'committed' as const, action:'task.category.create' as const, operationId:'op-category',
    occurrenceId:null, revision, state:'active' as const, cycle:null, archivedBy:null};
  f.element.view = state({outcome:saved});
  await f.element.updateComplete;
  expect(f.root.querySelector<HTMLInputElement>('#task-category-label')?.value).toBe('');
  choose('manage-task-category', category.id);
  choose('task-category', category.id);
  await f.input('task-title', 'Task draft');
  await f.input('task-description', 'Keep this');
  await f.input('task-category-label', 'Rename draft');
  submit(manager);
  expect(f.intents.at(-1)).toEqual({type:'renameCategory', categoryId:'garden', revision:'1', label:'Rename draft'});
  f.button('Archive category').click();
  expect(f.intents.at(-1)).toEqual({type:'archiveCategory', categoryId:'garden', revision:'1'});
  const updated = {...category, label:'Garden renamed', revision:revisionValue('2')};
  f.element.view = state({notice:'conflict', access:{...editable, categoryCatalog:{canManage:true, categories:[updated]}}});
  await f.element.updateComplete;
  expect(f.button('Rename category').disabled).toBe(true);
  expect(f.root.querySelector<HTMLInputElement>('#task-category-label')?.value).toBe('Rename draft');
  f.button('Review current category').click();
  await f.element.updateComplete;
  submit(manager);
  expect(f.intents.at(-1)).toEqual({type:'renameCategory', categoryId:'garden', revision:'2', label:'Rename draft'});
  f.element.view = state({notice:'invalid_input'});
  await f.element.updateComplete;
  expect(f.root.activeElement?.id).toBe('task-category-label');
  f.element.view = state({notice:'category_unavailable', access:{...editable, categoryCatalog:{canManage:true, categories:[]}}});
  await f.element.updateComplete;
  expect(f.root.querySelector('#task-category')?.getAttribute('aria-invalid')).toBe('true');
  expect(f.root.querySelector<HTMLInputElement>('#task-title')?.value).toBe('Task draft');
  expect(f.root.querySelector<HTMLInputElement>('#task-description')?.value).toBe('Keep this');
  expect(f.root.activeElement?.id).toBe('task-category');
  expect(f.button('Create task').disabled).toBe(true);
  submit(f.root.querySelector('#task-title')!.closest('form')!);
  expect(f.intents.at(-1)?.type).toBe('renameCategory');
  choose('manage-task-category', '');
  choose('task-category', '');
  await f.element.updateComplete;
  expect(f.button('Create task').disabled).toBe(false);
  f.element.view = state({scopeKey:'other', access:{...editable, categoryCatalog:{canManage:false, categories:[]}}});
  await f.element.updateComplete;
  expect(f.root.querySelector('#manage-task-category')).toBeNull();
  expect(f.root.querySelector<HTMLInputElement>('#task-title')?.value).toBe('');
});

test('classified task creation emits the selected category identity', async () => {
  const access = {...view().access!, categoryCatalog:{canManage:false, categories:[{id:'garden', label:'Garden', revision}]}};
  const f = await mount(view({access}));
  await f.input('task-title', 'Classified draft');
  const select = f.root.querySelector<HTMLSelectElement>('#task-category')!;
  select.value = 'garden';
  select.dispatchEvent(new Event('change', {bubbles:true}));
  await f.element.updateComplete;
  select.closest('form')!.dispatchEvent(new SubmitEvent('submit', {cancelable:true}));
  expect(f.intents).toEqual([{type:'create', title:'Classified draft', description:'', priority:'normal', categoryId:'garden'}]);
});

test('selected task requires a fresh review before its collaborative completion can be submitted', async () => {
  const f = await mount(view({detail: work}));
  f.element.participantNames = [{id: 'private-member-id', name: 'Owner'}, {id: 'peer', name: 'Helper'}];
  const allocationScope = {key: 'verified', context, definitionId: work.definitionId, readOnly: false, canManage: true,
    work: {occurrenceId: work.occurrenceId, revision, canComplete: true}};
  f.element.allocation = {scope: allocationScope, settings: null, review: null, busy: false, pending: false, notice: null};
  await f.element.updateComplete;
  const preview = f.root.querySelector('domus-allocation-preview')!;
  await preview.updateComplete;
  const peer = preview.shadowRoot!.querySelectorAll<HTMLInputElement>('input')[1];
  peer.checked = true; peer.dispatchEvent(new Event('change'));
  await preview.updateComplete; await f.element.updateComplete;
  expect(f.button('Mark done now').disabled).toBe(true);
  const form = f.root.querySelector('#complete-form')!;
  form.dispatchEvent(new Event('submit', {cancelable: true}));
  expect(f.intents).toEqual([]);
  const completion = {occurrenceId: work.occurrenceId, revision, performerIds: ['peer', 'private-member-id'], fingerprint: 'a'.repeat(64)};
  f.element.allocation = {...f.element.allocation, review: {completion, evidence: {mode: 'conserve_total', precision: 0,
    rounding: null, policyRevision: revision, taskOverride: false, base: 200, total: 200,
    shares: [['peer', 100], ['private-member-id', 100]], fingerprint: completion.fingerprint}}};
  await f.element.updateComplete; await preview.updateComplete; await f.element.updateComplete;
  expect(f.button('Mark done now').disabled).toBe(false);
  form.dispatchEvent(new Event('submit', {cancelable: true}));
  expect(f.intents).toEqual([{type: 'complete', materialUsages: null, reviewed: completion}]);
});

test('manual points wait for explicit reviewed amounts even before administrative settings load', async () => {
  const detail = {...work, completionPoints: 'manual' as const};
  const f = await mount(view({detail}));
  const submit = () => f.root.querySelector('#complete-form')!.dispatchEvent(new Event('submit', {cancelable: true}));
  expect(f.button('Mark done now').disabled).toBe(true);
  submit();
  expect(f.intents).toEqual([]);
  const scope = {key: 'verified', context, definitionId: work.definitionId, readOnly: false, canManage: true,
    work: {occurrenceId: work.occurrenceId, revision, canComplete: true, requiresManual: true}};
  f.element.participantNames = [{id: 'private-member-id', name: 'Owner'}];
  f.element.allocation = {scope, settings: null, busy: true, review: null, pending: false, notice: null};
  await f.element.updateComplete;
  const widget = f.root.querySelector('domus-allocation-preview')!;
  await widget.updateComplete;
  expect(widget.shadowRoot!.querySelector<HTMLInputElement>('input[type=text]')?.disabled).not.toBe(true);
  expect(widget.shadowRoot!.querySelector('fieldset')!.disabled).toBe(true);
  expect(f.button('Mark done now').disabled).toBe(true);
  f.element.allocation = {...f.element.allocation, busy: false};
  await f.element.updateComplete; await widget.updateComplete;
  expect(f.button('Mark done now').disabled).toBe(true);
  const input = widget.shadowRoot!.querySelector<HTMLInputElement>('input[type=text]')!;
  input.value = '1.25'; input.dispatchEvent(new Event('input')); await widget.updateComplete;
  const completion = {occurrenceId: work.occurrenceId, revision, performerIds: ['private-member-id'], fingerprint: 'a'.repeat(64),
    manualShares: [{member_id: 'private-member-id', amount_minor: 125}]};
  f.element.allocation = {...f.element.allocation, review: {completion, evidence: {mode: 'manual', precision: 2,
    rounding: null, policyRevision: revision, taskOverride: false, base: 200, total: 125,
    shares: [['private-member-id', 125]], fingerprint: completion.fingerprint}}};
  await f.element.updateComplete; await widget.updateComplete; await f.element.updateComplete;
  expect(f.button('Mark done now').disabled).toBe(false);
  submit();
  expect(f.intents).toEqual([{type: 'complete', materialUsages: null, reviewed: completion}]);
  f.element.allocation = {...f.element.allocation, scope: {...scope, work: {...scope.work, revision: revisionValue('2')}}};
  await f.element.updateComplete;
  expect(f.button('Mark done now').disabled).toBe(true);
});

test.each(['en', 'es'] as const)('manual allocation gives a non-manager a localized next action in %s', async locale => {
  const f = await mount(view({detail: {...work, allowedActions: ['claim'], completionPoints: 'manager_required'}}), locale);
  expect(f.root.querySelector('#complete-form')).toBeNull();
  expect(f.text()).toContain(locale === 'en' ? 'Ask a points administrator to record this work' : 'Pide a un administrador de puntos que registre el trabajo');
});

test.each(['en','es'] as const)('%s earlier usage keeps explicit actions, reason drafts, navigation and keyboard focus after reopening', async language => {
  const material={intentId:'old-intent',cycleId:'old-cycle',lineId:'line-1',revision, effectRevision:'1',submittedQuantity:null,quantity:null,
    state:'pending_recording' as const,pendingReason:'actual_quantity_required',confirmedQuantity:null,confirmedEffectRevision:null,movementId:null,postedAt:null};
  const current:TaskDetail={...work,materials:[{lineId:'line-1',label:'QA Soap',plannedQuantity:'2',precision:0,unitId:'piece',locationId:'pantry'}]};
  const group={cycle:{cycleId:'old-cycle',verification:'none' as const,performedAt:'100',performerIds:['private-member-id']},closedAt:'200',materialOutcomes:[material],allowedActions:['materials.settle']};
  const f=await mount(view({detail:current}),language);
  const t=(en:string,es:string)=>language==='en'?en:es;
  const pressHistory=async(label:string)=>{const button=[...f.root.querySelectorAll<HaButton>('vyp-ha-button')].find(item=>item.state.label===label)!;
    await button.updateComplete;button.click();await f.element.updateComplete;};
  await pressHistory(t('Review earlier usage','Revisar consumos anteriores'));
  expect(f.intents.at(-1)).toEqual({type:'materialHistory',more:false});
  f.element.view=view({phase:'loading',busy:true});await f.element.updateComplete;
  f.element.view=view({detail:current,materialHistory:{items:[group],nextCursor:'next'}});await f.element.updateComplete;
  expect(f.root.activeElement).toBe(f.root.querySelector('#material-history-heading'));
  const history=f.root.querySelector('#material-history-heading')!.parentElement!;
  const component=history.querySelector('domus-task-material-outcomes')!;await component.updateComplete;
  const fields=component.shadowRoot!.querySelectorAll<HaTextField>('vyp-ha-field');
  fields[0].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'0'}}));
  await f.element.updateComplete;await component.updateComplete;
  fields[1].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'QA nothing used'}}));
  await f.element.updateComplete;await component.updateComplete;
  const save=component.shadowRoot!.querySelector<HaButton>('vyp-ha-button')!;await save.updateComplete;save.click();
  expect(f.intents.at(-1)).toMatchObject({type:'settleMaterial',occurrenceId:'work-1',cycleId:'old-cycle',intentId:'old-intent',quantity:'0',reason:'QA nothing used'});
  f.element.view=view({phase:'loading',busy:true});await f.element.updateComplete;
  f.element.view=view({detail:current,materialHistory:{items:[group],nextCursor:'next'},notice:'unavailable'});await f.element.updateComplete;
  expect(f.root.activeElement).toBe(f.root.querySelector('#material-history-heading'));
  const restored=f.root.querySelector('#material-history-heading')!.parentElement!.querySelector('domus-task-material-outcomes')!;await restored.updateComplete;
  expect(restored.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!.value).toBe('0');
  await pressHistory(t('Next closed completion','Siguiente realización cerrada'));
  expect(f.intents.at(-1)).toEqual({type:'materialHistory',more:true});
  f.element.view=view({detail:current,materialHistory:{items:[],nextCursor:null}});await f.element.updateComplete;
  expect(f.text()).toContain(t('No earlier completions.','No hay realizaciones anteriores.'));
});

test.each(['en','es'] as const)('%s completion review localizes exact planned decimal quantities without changing the command', async locale => {
  const f=await mount(view({detail:{...work,materials:[{lineId:'soap',label:'QA Soap',plannedQuantity:'1.25',precision:6,unitId:'millilitre',locationId:'pantry'}]}}),locale);
  const form=f.root.querySelector('#complete-form')!;
  expect(form.textContent).toContain((locale==='es'?'Cantidad prevista: 1,25':'Planned quantity: 1.25'));
  form.dispatchEvent(new SubmitEvent('submit',{cancelable:true}));
  expect(f.intents.at(-1)).toMatchObject({type:'complete',materialUsages:[{line_id:'soap',quantity:'1.25'}]});
});
