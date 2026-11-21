import {afterEach, expect, test} from 'vitest';
import type {HaButton} from '@vypdev/ha-ui/button';
import type {HaTextField} from '@vypdev/ha-ui/field';
import type {HaSelect} from '@vypdev/ha-ui/select';
import {revisionValue} from '../src/domain/administration';
import type {TaskDetail, TaskMaterialOutcome} from '../src/domain/tasks';
import type {TaskMaterialPlanView} from '../src/application/task-material-planning';
import type {MaterialPlanIntent} from '../src/presentation/domus-task-material-plan';
import type {MaterialRecordingDrafts, MaterialSettlementIntent} from '../src/presentation/domus-task-material-outcomes';
import {materialMessage, materialSource, materialUnit} from '../src/presentation/task-material-messages';
import '../src/presentation/domus-task-material-plan';
import '../src/presentation/domus-task-material-outcomes';
const mounted: HTMLElement[] = [];
afterEach(() => {mounted.splice(0).forEach(element => element.remove());});
const r = revisionValue('7');
const initial: TaskMaterialPlanView = {open:false, busy:false, canLink:true, readOnly:false, rows:[], choices:[], cursor:null, notice:null};
function material(patch: Partial<TaskMaterialOutcome> = {}): TaskMaterialOutcome {
  return {intentId:'intent-1', cycleId:'cycle-1', lineId:'line-1', revision:r, effectRevision:'1', submittedQuantity:null,
    quantity:null, state:'pending_recording', pendingReason:'actual_quantity_required', confirmedQuantity:null,
    confirmedEffectRevision:null, movementId:null, postedAt:null, ...patch};
}
function work(values: readonly TaskMaterialOutcome[], allowed = true): TaskDetail {
  return {occurrenceId:'work-1', definitionId:'definition-1', definitionRevision:revisionValue('1'), title:'Clean',
    description:'', priority:'normal', state:'completed', revision:revisionValue('2'), assigneeIds:[], dueAt:null,
    currentCycleId:'cycle-1', allowedActions:allowed ? ['materials.settle'] : [],
    cycle:{cycleId:'cycle-1', verification:'pending', performedAt:'1000', performerIds:['member-1']},
    materials:values.map(value => ({lineId:value.lineId, label:'<b>Soap</b>', plannedQuantity:'2', precision:6, unitId:'millilitre', locationId:'pantry'})),
    materialOutcomes:values, materialRecording:'separate_recording', dependencyReviewRequired:false, pendingMaterials:true};
}
async function press(element: HTMLElement, label: string) {
  const control = [...element.shadowRoot!.querySelectorAll<HaButton>('vyp-ha-button')].find(button => button.state.label === label)!;
  await control.updateComplete; control.click(); return control;
}
test.each(['en','es'] as const)('%s plan loads explicitly and uses published controls with exact quantity proposals', async language => {
  const element = document.createElement('domus-task-material-plan'); element.language=language; element.view=initial;
  const intents: MaterialPlanIntent[] = [];
  element.addEventListener('domus-material-plan-intent', event => intents.push((event as CustomEvent<MaterialPlanIntent>).detail));
  document.body.append(element); mounted.push(element); await element.updateComplete;
  await press(element, materialMessage('open', language)); expect(intents).toEqual([{action:'load'}]);
  const choice = {referenceId:'soap', name:'<b>Soap</b>', unit:'millilitre' as const};
  element.view={...initial, open:true, choices:[choice], cursor:'next', rows:[{referenceId:'soap', input:'0', choice}]};
  await element.updateComplete;
  expect(element.shadowRoot!.querySelector('b')).toBeNull();
  expect(element.shadowRoot!.textContent).toContain('<b>Soap</b>');
  expect(element.shadowRoot!.textContent).toContain(materialSource('pantry', language));
  const select = element.shadowRoot!.querySelector<HaSelect>('vyp-ha-select')!;
  expect(select.state.options[0]).toMatchObject({value:'soap', disabled:true});
  select.dispatchEvent(new CustomEvent('ha-select-request', {detail:{value:'other'}}));
  select.dispatchEvent(new CustomEvent('ha-select-request', {detail:{value:null}}));
  const field = element.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!;
  expect(field.value).toBe('0'); expect(field.state.error).toBe('');
  field.dispatchEvent(new CustomEvent('ha-value-request', {detail:{value:'1,25'}}));
  await press(element, materialMessage('more', language));
  await press(element, materialMessage('refresh', language));
  await press(element, materialMessage('remove', language));
  await press(element, materialMessage('clear', language));
  expect(intents.slice(1)).toEqual([{action:'add',referenceId:'other'}, {action:'edit',referenceId:'soap',input:'1,25'},
    {action:'more'},{action:'load'},{action:'remove',referenceId:'soap'},{action:'clear'}]);
  element.view={...initial, open:true, rows:[{referenceId:'soap', input:'0.5', choice:{...choice, unit:'piece'}}]};
  await element.updateComplete;
  expect(element.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!.state.error).toBe(materialMessage('invalidQuantity',language));
  element.view={...initial, open:true, canLink:false, notice:'forbidden', rows:[{referenceId:'soap',input:'0.5',choice:null}]};
  await element.updateComplete;
  expect(element.shadowRoot!.textContent).not.toContain('<b>Soap</b>');
  expect(element.shadowRoot!.textContent).toContain(materialMessage('unreviewed',language));
  expect(element.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!.disabled).toBe(true);
});
test('plan limits, empty catalog, loading and unavailable states retain a clear title-only path', async () => {
  const element = document.createElement('domus-task-material-plan'); document.body.append(element); mounted.push(element);
  await element.updateComplete; expect(element.shadowRoot!.querySelector('section')).toBeNull();
  element.view={...initial, canLink:false}; await element.updateComplete; expect(element.shadowRoot!.querySelector('section')).toBeNull();
  element.view={...initial,open:true}; await element.updateComplete; expect(element.shadowRoot!.textContent).toContain(materialMessage('empty','en'));
  element.view={...initial,open:true,busy:true}; await element.updateComplete; expect(element.shadowRoot!.textContent).not.toContain(materialMessage('empty','en'));
  const choice={referenceId:'a',name:'Soap',unit:'gram' as const};
  element.view={...initial,open:true,notice:'unavailable',rows:Array.from({length:32},(_,i) => ({referenceId:'p'+i,input:'1',choice})),choices:[choice]};
  await element.updateComplete; expect(element.shadowRoot!.textContent).toContain(materialMessage('limit','en'));
  expect(element.shadowRoot!.querySelector<HaSelect>('vyp-ha-select')!.disabled).toBe(true);
  element.disabled=true; await element.updateComplete;
  expect(element.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!.disabled).toBe(true);
});
test.each(['en','es'] as const)('%s an empty denied plan explains the loss of linking access', async language => {
  const element=document.createElement('domus-task-material-plan');element.language=language;
  element.view={...initial,open:true,canLink:false,notice:'forbidden'};
  document.body.append(element);mounted.push(element);await element.updateComplete;
  expect(element.shadowRoot!.querySelector('[role="alert"]')?.textContent).toBe(materialMessage('forbiddenEmpty',language));
  expect(element.shadowRoot!.querySelector('vyp-ha-select')).toBeNull();
  const refresh=element.shadowRoot!.querySelector<HaButton>('vyp-ha-button')!;
  await refresh.updateComplete;expect(refresh.disabled).toBe(true);
});
test.each(['en','es'] as const)('%s actual recording retains zero and reason, and requires review of a concurrent intent revision', async language => {
  const element = document.createElement('domus-task-material-outcomes'); element.language=language; element.work=work([material()]);
  const settled: MaterialSettlementIntent[] = [];
  element.addEventListener('domus-material-settlement-intent', event => settled.push((event as CustomEvent<MaterialSettlementIntent>).detail));
  element.addEventListener('domus-material-recording-draft', event => {
    const {intentId,draft}=(event as CustomEvent<{intentId:string;draft:MaterialRecordingDrafts[string]}>).detail;
    element.drafts={...element.drafts,[intentId]:draft};
  });
  document.body.append(element); mounted.push(element); await element.updateComplete;
  const inputs=()=>[...element.shadowRoot!.querySelectorAll<HaTextField>('vyp-ha-field')];
  expect((await press(element,materialMessage('record',language))).disabled).toBe(true);
  inputs()[0].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'0'}})); await element.updateComplete;
  inputs()[1].dispatchEvent(new CustomEvent('ha-value-request',{detail:{value:'Not used <soap>'}})); await element.updateComplete;
  expect(element.drafts['intent-1']).toEqual({revision:r,quantity:'0',reason:'Not used <soap>'});
  await press(element,materialMessage('record',language));
  expect(settled).toEqual([{occurrenceId:'work-1',intentId:'intent-1',cycleId:'cycle-1',revision:r,quantity:'0',reason:'Not used <soap>'}]);
  element.work=work([material({revision:revisionValue('8')})]); await element.updateComplete;
  expect(element.shadowRoot!.textContent).toContain(materialMessage('changed',language));
  expect((await press(element,materialMessage('record',language))).disabled).toBe(true);
  await press(element,materialMessage('review',language)); await element.updateComplete;
  expect(element.drafts['intent-1']).toEqual({revision:'8',quantity:'0',reason:'Not used <soap>'});
  element.shadowRoot!.querySelector('form')!.dispatchEvent(new SubmitEvent('submit',{cancelable:true}));
  expect(settled[1].revision).toBe('8');
  element.work=work([material()],false); await element.updateComplete;
  expect(element.shadowRoot!.textContent).toContain(materialMessage('denied',language));
  expect(inputs()[0].value).toBe('0');
  element.disabled=true; await element.updateComplete; expect(inputs()[0].disabled).toBe(true);
});
test('per-line outcomes distinguish confirmed, unused and pending totals without offering a new posted correction', async () => {
  const element=document.createElement('domus-task-material-outcomes'); const intents:MaterialSettlementIntent[]=[];
  element.addEventListener('domus-material-settlement-intent',event=>intents.push((event as CustomEvent<MaterialSettlementIntent>).detail));
  document.body.append(element); mounted.push(element); await element.updateComplete;
  expect(element.shadowRoot!.querySelector('section')).toBeNull();
  const pending=material({quantity:'3',submittedQuantity:'3',state:'pending_regularization',pendingReason:'insufficient_stock'});
  const posted=material({intentId:'posted',lineId:'line-2',quantity:'1',confirmedQuantity:'1',state:'posted',pendingReason:null,movementId:'move',confirmedEffectRevision:revisionValue('1')});
  const unused=material({intentId:'unused',lineId:'line-3',quantity:'0',state:'not_used',pendingReason:null});
  element.work=work([pending,posted,unused]); await element.updateComplete;
  expect(element.shadowRoot!.querySelectorAll('li')).toHaveLength(3);
  expect(element.shadowRoot!.querySelectorAll('vyp-ha-button')).toHaveLength(1);
  await press(element,materialMessage('settle','en'));
  expect(intents).toEqual([{occurrenceId:'work-1',intentId:'intent-1',cycleId:'cycle-1',revision:r}]);
  const corrected=material({...pending,confirmedQuantity:'1',confirmedEffectRevision:revisionValue('1')});
  element.work=work([corrected]); await element.updateComplete;
  expect(element.shadowRoot!.textContent).toContain(materialMessage('pendingTotal','en'));
  element.work={...work([pending]),materials:[{lineId:'line-1',label:'',plannedQuantity:'2',precision:0}]};
  await element.updateComplete; expect(element.shadowRoot!.textContent).toContain(materialMessage('unreviewed','en'));
  element.work=work([material()]); element.drafts={'intent-1':{revision:r,quantity:'no',reason:''}}; await element.updateComplete;
  expect(element.shadowRoot!.querySelector<HaTextField>('vyp-ha-field')!.state.error).toBe(materialMessage('invalidQuantity','en'));
});
test('units and sources use captured server identifiers and never infer pieces or Pantry from precision', () => {
  expect(materialUnit('piece','en')).toBe('pieces'); expect(materialUnit('gram','es')).toBe('g'); expect(materialUnit('millilitre','en')).toBe('mL');
  expect(materialUnit('piece','en','1')).toBe('piece'); expect(materialUnit('piece','es','1')).toBe('unidad');
  expect(materialUnit('legacy-unit','en')).toBe('Unit code: legacy-unit'); expect(materialUnit(undefined,'es')).toBe('Código de unidad: No disponible');
  expect(materialSource('utility-room','en')).toBe('Source: utility-room'); expect(materialSource(undefined,'en')).toBe('Source: Unavailable');
});

test('disabled form and button events cannot bypass the explicit material action guard', async () => {
  const element=document.createElement('domus-task-material-outcomes'); let events=0;
  element.addEventListener('domus-material-settlement-intent',()=>events++);
  element.work=work([material()]); element.disabled=true;
  document.body.append(element); mounted.push(element); await element.updateComplete;
  element.shadowRoot!.querySelector('form')!.dispatchEvent(new SubmitEvent('submit',{cancelable:true}));
  element.shadowRoot!.querySelector('vyp-ha-button')!.dispatchEvent(new MouseEvent('click'));
  element.work=work([material({quantity:'2',state:'pending_regularization'})]); await element.updateComplete;
  element.shadowRoot!.querySelector('vyp-ha-button')!.dispatchEvent(new MouseEvent('click'));
  expect(events).toBe(0);
});
