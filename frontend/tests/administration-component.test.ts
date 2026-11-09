import {afterEach, expect, test} from 'vitest';
import {DomusAdministration} from '../src/presentation/domus-administration';
import type {AdministrationIntent} from '../src/presentation/domus-administration';
import type {AdministrationView} from '../src/application/administration-controller';
import {revisionValue} from '../src/domain/administration';
import {administrationMessage} from '../src/presentation/administration-messages';

const context = {installationId:'01234567-89ab-cdef-0123-456789abcdef',channel:'edge' as const,subject:'a'.repeat(32)};
const member = {memberId:'owner',haUserId:context.subject,role:'viewer' as const,status:'active' as const,
  revision:revisionValue('3'),exceptions:[]};
const presentation = {memberId:'owner',alias:'My alias',revision:revisionValue('11')};
function view(extra: Partial<AdministrationView> = {}): AdministrationView {
  return {phase:'ready',busy:false,session:{context,deployment:'standalone',access:'full',serverTime:1000,
    expiresAt:100000,householdApiAvailable:true},access:{state:'active',setupAllowed:false,enrollmentAllowed:false,
    member,effectiveRole:'administrator',policyRevision:revisionValue('5'),permissions:['household.read','household.manage',
      'members.read','members.manage','policy.manage','preferences.read','preferences.write','operations.read']},
    capabilities:{contractVersion:2,householdId:'home',actions:['household.update','member.update','policy.update','member.presentation.update','member.preferences.update']},
    household:{householdId:'home',name:'Household',timeZone:'UTC',revision:revisionValue('7')},
    policy:{householdId:'home',revision:revisionValue('5'),mappingMode:'all_ha_administrators',targetHAUserId:null,
      adjustments:[{role:'restricted',permission:'shopping.request',allow:false}]},
    directory:{state:'available',profiles:[{haUserId:context.subject,name:'Verified owner'},{haUserId:'b'.repeat(32),name:'Pending member'}]},
    presentation,preferences:{memberId:'owner',locale:'es',routine_participation_summaries:true,revision:revisionValue('13'),notificationDelivery:'unavailable'},
    roster:{directoryState:'available',members:[{member,presentation,metadata:{state:'available',name:'Verified owner',avatarState:'unavailable'}},
      {member:{...member,memberId:'other',haUserId:'b'.repeat(32),status:'pending'},presentation:{...presentation,memberId:'other',alias:null},
        metadata:{state:'available',name:'Pending member',avatarState:'unavailable'}}]},
    errors:{},notice:null,outcome:null,journal:{context,observedAt:1000,records:[]},
    controls:{household:true,policy:true,preferences:true,ownAlias:true,memberIds:['owner','other'],aliasMemberIds:['other'],recoverableKeys:[],dismissibleKeys:[]},...extra};
}
const owned: DomusAdministration[] = [];
afterEach(()=>{for(const element of owned.splice(0)) element.remove();});
async function mount(value: AdministrationView|null = view(), locale:'en'|'es'='en') {
  const element = document.createElement('domus-administration'); element.view=value; element.language=locale;
  const intents:AdministrationIntent[]=[];
  element.addEventListener('domus-administration-intent',event=>{
    const actual=event as CustomEvent<AdministrationIntent>;expect(actual.bubbles).toBe(true);expect(actual.composed).toBe(true);
    expect(Object.isFrozen(actual.detail)).toBe(true);intents.push(actual.detail);
  });
  document.body.append(element);owned.push(element);await element.updateComplete;const root=element.shadowRoot!;
  const button=(name:string)=>[...root.querySelectorAll('button')].find(item=>(item.getAttribute('aria-label')??item.textContent?.trim())===name)!;
  const click=async(name:string)=>{expect(button(name),name).toBeDefined();button(name).click();await element.updateComplete;};
  const input=(name:string)=>{
    const label=[...root.querySelectorAll('label')].find(item=>item.textContent?.trim()===name)!;expect(label,name).toBeDefined();
    return root.getElementById(label.htmlFor) as HTMLInputElement|HTMLSelectElement;
  };
  const change=async(name:string,value:string|boolean)=>{
    const field=input(name);if(typeof value==='boolean'){expect(field).toBeInstanceOf(HTMLInputElement);(field as HTMLInputElement).checked=value;}
    else field.value=value;
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement||field.type==='checkbox'?'change':'input',{bubbles:true}));await element.updateComplete;
  };
  return {element,root,intents,button,click,input,change,text:()=>root.textContent!};
}

test('HADB-03: the owned widget shows current stored and effective roles without emitting work',async()=>{
  const f=await mount();expect(f.element).toBeInstanceOf(DomusAdministration);expect(f.text()).toContain('Verified owner');
  expect(f.text()).toContain('Viewer');expect(f.text()).toContain('Administrator');expect(f.text()).toContain('Pending member');
  expect(f.text()).not.toContain(context.installationId);expect(f.text()).not.toContain(context.subject);expect(f.intents).toEqual([]);
});
test('household-browser-C15: hostile HA names and aliases remain inert text',async()=>{
  const current=view();const hostile='<img src=x onerror=alert(1)>';
  const f=await mount({...current,presentation:{...presentation,alias:hostile},roster:{...current.roster!,members:[
    {...current.roster!.members[0],presentation:{...presentation,alias:hostile},metadata:{state:'available',name:hostile,avatarState:'unavailable'}}]}});
  expect(f.text()).toContain(hostile);expect(f.root.querySelector('img,script')).toBeNull();expect(f.intents).toEqual([]);
});
test('HADW-01: own alias requires review then explicit confirmation with its independent exact revision',async()=>{
  const f=await mount(view({presentation:{...presentation,revision:revisionValue('9007199254740993')}}));
  await f.click('Edit own alias');await f.change('Domus alias','  Literal <b>name</b>  ');await f.click('Review changes');
  expect(f.intents).toEqual([]);expect(f.text()).toContain('9007199254740993');await f.click('Save changes');
  expect(f.intents).toEqual([{type:'submit',command:{action:'member.presentation.update',memberId:'owner',
    payload:{expected_revision:'9007199254740993',alias:'  Literal <b>name</b>  '}}}]);
  expect(f.button('Save changes').disabled).toBe(true);expect(f.root.querySelector('b')).toBeNull();
});
test('HADW-01: clearing an alias requires the explicit HA-name choice rather than an empty value',async()=>{
  const f=await mount();await f.click('Edit own alias');await f.change('Domus alias','');await f.click('Review changes');
  expect(f.root.querySelector('[role=alert]')).not.toBeNull();expect(f.intents).toEqual([]);
  await f.change('Use Home Assistant name',true);await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{expected_revision:'11',alias:null}}});
});
test('HADW-02: own preference values have their own revision and honest unavailable delivery',async()=>{
  const f=await mount();await f.click('Edit preferences');await f.change('Saved language','en');
  await f.change('Routine participation summaries',false);await f.click('Review changes');await f.click('Save changes');
  expect(f.intents).toEqual([{type:'submit',command:{action:'member.preferences.update',payload:{expected_revision:'13',locale:'en',routine_participation_summaries:false}}}]);
  expect(f.text()).toContain('Notification delivery is unavailable');
});
test('HADW-04: household edits retain the original revision and exact timezone until explicit submission',async()=>{
  const f=await mount();await f.click('Edit household');await f.change('New household name','Family');await f.change('New timezone','Europe/Madrid');
  await f.click('Review changes');await f.click('Save changes');expect(f.intents).toEqual([{type:'submit',command:{action:'household.update',
    payload:{expected_revision:'7',name:'Family',time_zone:'Europe/Madrid'}}}]);
});
test('HADW-04: pending activation defaults to restricted and needs an explicit access confirmation',async()=>{
  const f=await mount();await f.click('Manage participant: Pending member');expect(f.input('Household profile').value).toBe('restricted');
  await f.change('Membership status','active');await f.click('Review changes');expect(f.intents).toEqual([]);
  expect(f.root.querySelector('[role=alert]')).not.toBeNull();await f.change('Approve household access',true);
  await f.click('Review changes');await f.click('Save changes');expect(f.intents).toEqual([{type:'submit',command:{action:'member.update',memberId:'other',
    payload:{expected_revision:'3',role:'restricted',status:'active',exceptions:[]}}}]);
});
test('HADW-05: a profile adjustment preserves the untouched mapping and other profile rules',async()=>{
  const f=await mount();await f.click('Edit access rules');await f.change('Profile to customize','adult');
  await f.change('View household','deny');await f.click('Review changes');await f.click('Save changes');
  const intent=f.intents[0];expect(intent.type).toBe('submit');if(intent.type!=='submit')throw new Error('Expected explicit policy intent');
  expect(intent.command).toMatchObject({action:'policy.update',payload:{expected_revision:'5',mapping_mode:'all_ha_administrators',target_ha_user_id:null}});
  if(intent.command.action!=='policy.update')throw new Error('Expected policy action');
  expect(intent.command.payload.adjustments).toHaveLength(2);expect(intent.command.payload.adjustments).toEqual(expect.arrayContaining([
    {role:'restricted',permission:'shopping.request',allow:false},{role:'adult',permission:'household.read',allow:false}]));
});
test('household-browser-C17: translation and a newer current fact do not rebase a safe alias draft',async()=>{
  const f=await mount();await f.click('Edit own alias');await f.change('Domus alias','Local draft');
  f.element.language='es';f.element.view=view({presentation:{...presentation,alias:'Remote value',revision:revisionValue('12')}});await f.element.updateComplete;
  expect(f.input('Alias de Domus').value).toBe('Local draft');await f.click('Revisar cambios');await f.click('Guardar cambios');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{expected_revision:'11',alias:'Local draft'}}});
});
test('household-browser-C13: same-account member replacement cannot retain the former private preference draft',async()=>{
  const f=await mount();await f.click('Edit preferences');await f.change('Saved language','en');
  const next=view();f.element.view={...next,access:{...next.access!,member:{...member,memberId:'replacement'}},
    presentation:{...presentation,memberId:'replacement'},preferences:{...next.preferences!,memberId:'replacement'}};
  await f.element.updateComplete;await f.click('Edit preferences');expect(f.input('Saved language').value).toBe('es');expect(f.intents).toEqual([]);
});
test('HADB-01: checking hides private form values and preserves only a same-owner draft until proof returns',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit own alias');await f.change('Domus alias','Unsent private draft');
  f.element.pending=true;f.element.view=null;await f.element.updateComplete;expect(f.text()).not.toContain('Unsent private draft');
  expect(f.root.querySelector('input')).toBeNull();f.element.pending=false;f.element.view=current;await f.element.updateComplete;
  expect(f.input('Domus alias').value).toBe('Unsent private draft');f.element.retired=true;f.element.view=null;await f.element.updateComplete;
  f.element.retired=false;f.element.view=current;await f.element.updateComplete;await f.click('Edit own alias');
  expect(f.input('Domus alias').value).toBe('My alias');expect(f.intents).toEqual([]);
});
test('HADB-03: application controls govern visible edits even when an old permission label still appears',async()=>{
  const current=view(),f=await mount({...current,controls:{...current.controls,household:false,policy:false,preferences:false,ownAlias:false,memberIds:[],aliasMemberIds:[]}});
  expect(f.button('Edit own alias').disabled).toBe(true);expect(f.button('Edit preferences').disabled).toBe(true);
  f.button('Edit preferences').click();expect(f.root.querySelector('form')).toBeNull();expect(f.intents).toEqual([]);
});
test('HADW-05: an HA account with pending household membership is not offered as a new mapping target',async()=>{
  const f=await mount();await f.click('Edit access rules');await f.change('HA administrator mapping','selected_ha_user');
  const options=[...(f.input('Target Home Assistant account') as HTMLSelectElement).options];
  expect(options.some(option=>option.value===context.subject)).toBe(true);expect(options.some(option=>option.value==='b'.repeat(32))).toBe(false);
});
test('HADW-05: unavailable directory facts retain the stored target visibly while other profile rules remain editable',async()=>{
  const current=view();const f=await mount({...current,directory:{state:'denied',profiles:[]},policy:{...current.policy!,mappingMode:'selected_ha_user',targetHAUserId:context.subject}});
  await f.click('Edit access rules');const target=f.input('Target Home Assistant account');expect(target.value).toBe(context.subject);expect(target.disabled).toBe(true);
  await f.change('View household','allow');await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{mapping_mode:'selected_ha_user',target_ha_user_id:context.subject}}});
});
test('HADW-05: explicitly switching to all HA administrators clears the formerly captured target',async()=>{
  const current=view(),f=await mount({...current,policy:{...current.policy!,mappingMode:'selected_ha_user',targetHAUserId:context.subject}});
  await f.click('Edit access rules');await f.change('HA administrator mapping','all_ha_administrators');await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{mapping_mode:'all_ha_administrators',target_ha_user_id:null}}});
});
test('HADW-05: an explicitly selected active participant remains a distinct target rather than a display-name identity',async()=>{
  const current=view(),other=current.roster!.members[1];const f=await mount({...current,roster:{...current.roster!,members:[current.roster!.members[0],{...other,member:{...other.member,status:'active'}}]}});
  await f.click('Edit access rules');await f.change('HA administrator mapping','selected_ha_user');await f.change('Target Home Assistant account','b'.repeat(32));
  await f.click('Review changes');await f.click('Save changes');expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{target_ha_user_id:'b'.repeat(32)}}});
});

const draftFactCases = [
  {kind:'household', open:'Edit household', field:'New household name', value:'Private household draft',
    missing:(current:AdministrationView):AdministrationView=>({...current,household:null,controls:{...current.controls,household:false}})},
  {kind:'preferences', open:'Edit preferences', field:'Saved language', value:'en',
    missing:(current:AdministrationView):AdministrationView=>({...current,preferences:null,controls:{...current.controls,preferences:false}})},
  {kind:'own alias', open:'Edit own alias', field:'Domus alias', value:'Private own alias draft',
    missing:(current:AdministrationView):AdministrationView=>({...current,presentation:null,roster:null,controls:{...current.controls,ownAlias:false,memberIds:[],aliasMemberIds:[]}})},
  {kind:'other alias', open:'Change alias: Pending member', field:'Domus alias', value:'Private other alias draft',
    missing:(current:AdministrationView):AdministrationView=>({...current,roster:null,controls:{...current.controls,memberIds:[],aliasMemberIds:[]}})},
  {kind:'member', open:'Manage participant: Pending member', field:'Household profile', value:'adult',
    missing:(current:AdministrationView):AdministrationView=>({...current,roster:{...current.roster!,members:current.roster!.members.map(row=>({...row,member:{...row.member,exceptions:null}}))},controls:{...current.controls,memberIds:[]}})},
  {kind:'policy', open:'Edit access rules', field:'Profile to customize', value:'restricted',
    missing:(current:AdministrationView):AdministrationView=>({...current,policy:null,controls:{...current.controls,policy:false}})},
];
for(const scenario of draftFactCases) test('HADB-03: '+scenario.kind+' drafts hide when current readable facts disappear and return only to the same owner',async()=>{
  const current=view(),f=await mount(current);await f.click(scenario.open);
  if(scenario.kind==='other alias')await f.change('Use Home Assistant name',false);
  await f.change(scenario.field,scenario.value);
  f.element.view=scenario.missing(current);await f.element.updateComplete;
  expect(f.root.querySelector('form, input, select'),scenario.kind+' previous fields must be hidden').toBeNull();
  expect(f.text()).not.toContain('Original revision');expect(f.text()).toContain('This draft is hidden until its current data is available');
  expect(f.intents).toEqual([]);
  f.element.view=current;await f.element.updateComplete;expect(f.input(scenario.field).value).toBe(scenario.value);
  expect(f.intents).toEqual([]);
});
test('HADB-03: a confirmed private preference draft and its detached save callback stay hidden and inert after read loss',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit preferences');await f.change('Saved language','en');await f.click('Review changes');
  const save=f.button('Save changes');
  f.element.view={...current,preferences:null,controls:{...current.controls,preferences:false}};await f.element.updateComplete;
  expect(f.text()).not.toContain('Original revision');expect(f.text()).not.toContain('Saved language:');expect(f.button('Save changes')).toBeUndefined();
  save.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;expect(f.intents).toEqual([]);
  f.element.view=view({preferences:{...current.preferences!,locale:'es',revision:revisionValue('14')}});await f.element.updateComplete;
  await f.click('Save changes');expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{expected_revision:'13',locale:'en'}}});
});

test('HADW-01: own alias falls back to permitted roster facts independently of directory availability',async()=>{
  const current=view(),f=await mount({...current,presentation:null,directory:null});
  await f.click('Edit own alias');expect(f.input('Domus alias').value).toBe('My alias');
  await f.change('Use Home Assistant name',true);await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{expected_revision:'11',alias:null}}});
});
test('HADW-02: browser-language preferences explicitly save null without implying notification delivery',async()=>{
  const current=view(),f=await mount({...current,preferences:{...current.preferences!,locale:null,routine_participation_summaries:false}});
  await f.click('Edit preferences');expect(f.input('Saved language').value).toBe('');await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{locale:null,routine_participation_summaries:false}}});
  expect(f.text()).toContain('Follow the browser');expect(f.text()).toContain('sends no notification');
});
test('HADB-02: only explicit reset adopts newer facts; cancel and close restore focus without submitting',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Typed draft');
  f.element.view=view({household:{...current.household!,name:'Changed remotely',revision:revisionValue('8')}});await f.element.updateComplete;
  expect(f.input('New household name').value).toBe('Typed draft');await f.click('Reset from current data');
  expect(f.input('New household name').value).toBe('Changed remotely');expect(f.root.activeElement).toBe(f.input('New household name'));
  await f.click('Review changes');await f.click('Back to editing');expect(f.input('New household name').value).toBe('Changed remotely');
  await f.click('Review changes');await f.click('Save changes');expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{expected_revision:'8'}}});
  await f.click('Close editor');expect(f.root.activeElement).toBe(f.button('Edit household'));expect(f.root.querySelector('form')).toBeNull();
  await f.click('Edit household');await f.click('Cancel');expect(f.root.querySelector('form')).toBeNull();expect(f.intents).toHaveLength(1);
});
test('HADW-04: member exceptions change only selected ordinary grants and preserve unrelated decisions',async()=>{
  const current=view(),f=await mount({...current,roster:{...current.roster!,members:[{...current.roster!.members[0],member:{...member,
    exceptions:[{permission:'shopping.request',allow:true},{permission:'tasks.read',allow:false}]}}]}});
  await f.click('Manage participant: My alias');expect(f.input('Household profile').value).toBe('viewer');
  await f.change('View tasks','inherit');await f.change('View household','allow');await f.change('Request shopping','deny');
  await f.change('Household profile','adult');await f.change('Membership status','suspended');await f.click('Review changes');
  expect(f.text()).toContain('View household: Allow');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{action:'member.update',memberId:'owner',payload:{role:'adult',status:'suspended',
    exceptions:[{permission:'household.read',allow:true},{permission:'shopping.request',allow:false}]}}});
});
test('HADW-05: per-profile edits retain another role for the same permission and remove only the explicitly inherited rule',async()=>{
  const current=view(),f=await mount({...current,policy:{...current.policy!,adjustments:[
    {role:'restricted',permission:'household.read',allow:false},{role:'adult',permission:'household.read',allow:true}]}});
  await f.click('Edit access rules');await f.change('View household','deny');await f.change('View household','inherit');
  await f.change('Profile to customize','restricted');expect(f.input('View household').value).toBe('deny');
  await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{adjustments:[{role:'restricted',permission:'household.read',allow:false}]}}});
});
test('HADW-05: invalid injected profile and permission options show a bounded error and cannot become grants',async()=>{
  const f=await mount();await f.click('Edit access rules');
  for(const name of ['Profile to customize','View household']) {
    const select=f.input(name) as HTMLSelectElement,option=document.createElement('option');option.value='foreign';select.append(option);
    select.value='foreign';select.dispatchEvent(new Event('change'));await f.element.updateComplete;
    expect(f.root.querySelector('[role=alert]')?.textContent).toContain('Review these values');
  }
  expect(f.intents).toEqual([]);await f.click('Review changes');await f.click('Save changes');
  expect(f.intents[0]).toMatchObject({type:'submit',command:{payload:{adjustments:[{role:'restricted',permission:'shopping.request',allow:false}]}}});
});
test.each(['en','es'] as const)('household-admin-C02: %s null aliases show the verified HA name in both identity and roster',async locale=>{
  const current=view(),noAlias={...presentation,alias:null};
  const f=await mount({...current,presentation:noAlias,roster:{...current.roster!,members:[
    {...current.roster!.members[0],presentation:noAlias}] }},locale);
  expect(f.root.querySelector('.card strong')?.textContent).toBe('Verified owner');
  expect(f.root.querySelector('.people>li strong')?.textContent).toBe('Verified owner');
  expect(f.button((locale==='en'?'Manage participant':'Gestionar participante')+': Verified owner')).toBeDefined();
  expect(f.text()).not.toContain('My alias');expect(f.intents).toEqual([]);
});
test.each((['en','es'] as const).flatMap(locale=>(['absent','denied','unavailable'] as const).map(state=>[locale,state] as const)))(
  'household-admin-C02 / HADB-03: %s %s HA names retain their neutral label and distinct source fact',async(locale,state)=>{
  const current=view(),f=await mount({...current,presentation:{...presentation,alias:null},directory:{state:'unavailable',profiles:[]},
    roster:{directoryState:'unavailable',members:[{...current.roster!.members[0],presentation:{...presentation,alias:null},metadata:{state,name:null,avatarState:'unavailable'}}]}},locale);
  const fallback=locale==='en'?'Name unavailable':'Nombre no disponible';
  expect(f.root.querySelector('.card strong')?.textContent).toBe(fallback);
  expect(f.root.querySelector('.people>li strong')?.textContent).toBe(fallback);
  expect(f.text()).toContain(administrationMessage('metadata_'+state,locale));
  expect(f.text()).not.toContain('Verified owner');expect(f.text()).not.toContain(context.subject);expect(f.intents).toEqual([]);
});
test.each(['committed','historical'] as const)('HADB-02: %s original outcomes do not populate forms or substitute historical result values for current facts',async stage=>{
  const f=await mount(view({outcome:{kind:'receipt',stage,action:'member.presentation.update',operationId:'op_original',archivedBy:stage==='historical'?'restore_original':null,
    createdAt:1000,result:{memberId:'owner',alias:'Hidden historical alias',revision:revisionValue('1')},notificationDelivery:'unavailable',eventDelivery:null}}));
  expect(f.text()).toContain(stage==='historical'?'Its effect is absent from current state':'Review current facts');
  expect(f.text()).toContain('op_original');expect(f.text()).not.toContain('Hidden historical alias');
  await f.click('Edit own alias');expect(f.input('Domus alias').value).toBe('My alias');expect(f.intents).toEqual([]);
});
test.each([null,'correlation_original'])('HADB-02: rejected outcomes show safe reason/reference without claiming a submitted draft changed current facts (%s)',async correlationId=>{
  const f=await mount(view({notice:'conflict',outcome:{kind:'rejected',reason:'conflict',correlationId}}));
  expect(f.text()).toContain('Change not accepted');expect(f.text()).toContain('Your draft keeps its original revision');
  if(correlationId===null)expect(f.text()).not.toContain('Request reference');else expect(f.text()).toContain(correlationId);
  expect(f.intents).toEqual([]);
});
test('HADB-02: uncertain original outcome asks for explicit inspection and never sends automatically',async()=>{
  const f=await mount(view({outcome:{kind:'uncertain'}}));expect(f.text()).toContain('Outcome not confirmed');expect(f.intents).toEqual([]);
});
function originalRecords() {
  return (['prepared','uncertain','committed','historical','rejected'] as const).map((stage,index)=>({
    action:'member.preferences.update' as const,payload:{expected_revision:revisionValue('13'),locale:'es' as const,routine_participation_summaries:true},
    context,key:'original-'+index,createdAt:1000,expiresAt:3601000,stage,operationId:stage==='committed'||stage==='historical'?'op_'+index:null}));
}
test('HADB-02: bounded original rows expose no payload; only explicit currently allowed recovery and resolved dismissal emit intents',async()=>{
  const current=view(),records=originalRecords(),f=await mount({...current,session:{...current.session!,access:'read_only'},
    journal:{context,observedAt:1000,records},controls:{...current.controls,recoverableKeys:['original-0'],dismissibleKeys:['original-2']}});
  expect(f.root.querySelectorAll('.requests>li')).toHaveLength(5);expect(f.text()).not.toContain('expected_revision');expect(f.text()).not.toContain('routine_participation_summaries');
  const rows=[...f.root.querySelectorAll<HTMLLIElement>('.requests>li')],recover=rows[0].querySelector('button')!,dismiss=rows[2].querySelectorAll('button')[1];
  recover.click();dismiss.click();expect(f.intents).toEqual([{type:'recover',key:'original-0'},{type:'dismiss',key:'original-2'}]);
  f.element.view={...current,journal:{context,observedAt:1000,records},controls:{...current.controls,recoverableKeys:[],dismissibleKeys:[]}};await f.element.updateComplete;
  recover.dispatchEvent(new MouseEvent('click'));dismiss.dispatchEvent(new MouseEvent('click'));expect(f.intents).toHaveLength(2);
  f.element.pending=true;await f.element.updateComplete;recover.dispatchEvent(new MouseEvent('click'));expect(f.intents).toHaveLength(2);
});
test('HADB-01: inactive or unverified states discard drafts and offer only explicit refresh',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit preferences');await f.change('Saved language','en');
  f.element.view={...current,phase:'ready',session:null,access:null,notice:'authentication_required'};await f.element.updateComplete;
  expect(f.root.querySelector('form')).toBeNull();expect(f.text()).toContain('Previous private data is hidden');await f.click('Refresh administration');
  expect(f.intents).toEqual([{type:'refresh'}]);f.element.view=current;await f.element.updateComplete;await f.click('Edit preferences');
  expect(f.input('Saved language').value).toBe('es');await f.click('Cancel');await f.click('Refresh administration');expect(f.intents).toHaveLength(2);
});
test('HADB-01: disconnected widgets cannot retain private inputs when reattached',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Private disconnected draft');
  f.element.remove();expect(f.element.view).toBeNull();document.body.append(f.element);f.element.view=current;await f.element.updateComplete;
  await f.click('Edit household');expect(f.input('New household name').value).toBe('Household');expect(f.intents).toEqual([]);
});
for(const scenario of draftFactCases)test('HADB-01: a retained '+scenario.kind+' open callback cannot reopen unavailable facts',async()=>{
  const current=view(),f=await mount(current),open=f.button(scenario.open);
  f.element.view=scenario.missing(current);await f.element.updateComplete;open.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;
  expect(f.root.querySelector('form')).toBeNull();expect(f.intents).toEqual([]);
});
test('HADB-01: previously attached form events cannot edit, submit, reset or close drafts while current proof is hidden',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit access rules');const role=f.input('Profile to customize'),rule=f.input('View household');
  const reset=f.button('Reset from current data'),cancel=f.button('Cancel'),form=f.root.querySelector('form')!;
  f.element.pending=true;await f.element.updateComplete;role.value='restricted';role.dispatchEvent(new Event('change'));rule.value='allow';rule.dispatchEvent(new Event('change'));
  form.dispatchEvent(new Event('submit',{cancelable:true}));reset.dispatchEvent(new MouseEvent('click'));cancel.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;
  f.element.pending=false;await f.element.updateComplete;expect(f.input('Profile to customize').value).toBe('adult');expect(f.input('View household').value).toBe('inherit');expect(f.intents).toEqual([]);
});
test('HADB-01: an old review, alias input, checkbox and close callback cannot affect a replacement draft',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit own alias');const field=f.input('Domus alias'),clear=f.input('Use Home Assistant name'),form=f.root.querySelector('form')!;
  await f.click('Review changes');const save=f.button('Save changes'),back=f.button('Back to editing'),close=f.button('Close editor');
  await f.click('Reset from current data');field.value='Stale callback';field.dispatchEvent(new Event('input'));(clear as HTMLInputElement).checked=true;clear.dispatchEvent(new Event('change'));
  form.dispatchEvent(new Event('submit',{cancelable:true}));save.dispatchEvent(new MouseEvent('click'));back.dispatchEvent(new MouseEvent('click'));close.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;
  expect(f.input('Domus alias').value).toBe('My alias');expect((f.input('Use Home Assistant name') as HTMLInputElement).checked).toBe(false);expect(f.intents).toEqual([]);
});

test('HADB-03: unknown or inherited translation keys use a localized bounded unavailable message',()=>{
  expect(administrationMessage('foreign','en')).toBe(administrationMessage('notice_unavailable','en'));
  expect(administrationMessage('constructor','es')).toBe(administrationMessage('notice_unavailable','es'));
});
test('HADB-03: read-only current facts keep a draft inspectable but lock every edit until write access returns',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Unsent original');
  const open=f.button('Edit preferences');f.element.view={...current,session:{...current.session!,access:'read_only'},notice:'read_only',
    controls:{...current.controls,household:false,policy:false,preferences:false,ownAlias:false,memberIds:[],aliasMemberIds:[]}};await f.element.updateComplete;
  expect(f.input('New household name').value).toBe('Unsent original');expect(f.input('New household name').disabled).toBe(true);expect(f.text()).toContain('This form needs current write access');
  open.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;expect(f.root.querySelectorAll('form')).toHaveLength(1);expect(f.intents).toEqual([]);
  f.element.view=current;await f.element.updateComplete;expect(f.input('New household name').value).toBe('Unsent original');
});
test('HADB-01: hidden drafts can be explicitly closed without revealing their fields or sending work',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit preferences');f.element.view={...current,preferences:null,controls:{...current.controls,preferences:false}};await f.element.updateComplete;
  await f.click('Close editor');f.element.view=current;await f.element.updateComplete;expect(f.root.querySelector('form')).toBeNull();expect(f.intents).toEqual([]);
});
test('HADB-01: a cached open control is inert during checking, and an idle state offers truthful refresh guidance',async()=>{
  const current=view(),f=await mount(current),open=f.button('Edit household');f.element.pending=true;await f.element.updateComplete;
  open.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;expect(f.root.querySelector('form')).toBeNull();
  f.element.pending=false;f.element.view={...current,phase:'idle',notice:null};await f.element.updateComplete;
  expect(f.text()).toContain('The requested information is unavailable');await f.click('Refresh administration');expect(f.intents).toEqual([{type:'refresh'}]);
});
test('HADW-05: unnamed supported directory accounts remain explicit ID targets without a fabricated display name',async()=>{
  const current=view(),f=await mount({...current,directory:{state:'available',profiles:[{haUserId:context.subject,name:null}]}});
  await f.click('Edit access rules');await f.change('HA administrator mapping','setup_administrator');
  expect((f.input('Target Home Assistant account') as HTMLSelectElement).options[1].textContent).toContain('Name unavailable');expect(f.intents).toEqual([]);
});
test('HADB-02: a preflight conflict does not claim that an original server request exists',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Original draft');
  await f.click('Review changes');await f.click('Save changes');f.element.view={...current,notice:'conflict',outcome:null};await f.element.updateComplete;
  expect(f.text()).toContain('Your draft keeps its original revision');expect(f.text()).not.toContain('This request was submitted');
  expect(f.text()).not.toContain('Check its original result below');expect(f.intents).toHaveLength(1);
});
test('HADB-03: participant review names the exact target and its stable membership reference',async()=>{
  const f=await mount();await f.click('Manage participant: Pending member');await f.click('Review changes');
  const editor=f.root.querySelector('[role=region][aria-label="Manage participant"]')!;
  expect(editor.textContent).toContain('Participant: Pending member');expect(editor.querySelector('code')?.textContent).toBe('other');
  expect(f.intents).toEqual([]);
});

test.each([null,'Independently read alias'])('HADW-01: own alias target remains explicit without roster access (%s)',async alias=>{
  const current=view(),f=await mount({...current,roster:null,presentation:{...presentation,alias}});await f.click('Edit own alias');
  const editor=f.root.querySelector('[role=region][aria-label="Domus alias"]')!;expect(editor.textContent).toContain('Participant: '+(alias??'Verified owner'));
  expect(editor.querySelector('code')?.textContent).toBe('owner');expect(f.intents).toEqual([]);
});
test('household-admin-C58: invalid alias submission associates its error with the form controls and restores field focus',async()=>{
  const f=await mount();await f.click('Edit own alias');await f.change('Domus alias','');await f.click('Review changes');
  const error=f.root.querySelector<HTMLElement>('[role=alert]')!;expect(error).not.toBeNull();
  expect(f.root.activeElement).toBe(f.input('Use Home Assistant name'));
  for(const name of ['Use Home Assistant name','Domus alias'])expect(f.input(name).getAttribute('aria-describedby')).toBe(error.id);
  f.element.language='es';await f.element.updateComplete;expect(f.input('Alias de Domus').value).toBe('');
  expect(f.input('Alias de Domus').getAttribute('aria-describedby')).toBe(error.id);expect(f.intents).toEqual([]);
});
test('household-admin-C58: missing access approval focuses and describes the required confirmation without submitting',async()=>{
  const f=await mount();await f.click('Manage participant: Pending member');await f.change('Membership status','active');await f.click('Review changes');
  const approval=f.input('Approve household access'),error=f.root.querySelector<HTMLElement>('[role=alert]')!;
  expect(f.root.activeElement).toBe(approval);expect(approval.getAttribute('aria-describedby')).toBe(error.id);expect(f.intents).toEqual([]);
});
test('household-workspace-C50: back to editing restores the original field focus and keeps the unsent preference value',async()=>{
  const f=await mount();await f.click('Edit preferences');await f.change('Saved language','en');await f.click('Review changes');await f.click('Back to editing');
  expect(f.root.activeElement).toBe(f.input('Saved language'));expect(f.input('Saved language').value).toBe('en');expect(f.intents).toEqual([]);
});

for(const action of ['Back to editing','Cancel','Close editor','Close hidden editor'])test('household-workspace-C50: '+action+' keeps keyboard focus on a current enabled action after write access is lost',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Retained draft');
  if(action==='Back to editing'||action==='Close editor')await f.click('Review changes');
  f.element.view={...current,session:{...current.session!,access:'read_only'},notice:'read_only',
    household:action==='Close hidden editor'?null:current.household,controls:{...current.controls,household:false}};
  await f.element.updateComplete;
  const control=action==='Close hidden editor'?'Close editor':action;
  f.button(control).focus();expect(f.root.activeElement).toBe(f.button(control));await f.click(control);
  expect(f.root.activeElement).toBe(f.button('Refresh administration'));expect(f.button('Refresh administration').disabled).toBe(false);
  if(action==='Back to editing'){
    expect(f.input('New household name').value).toBe('Retained draft');expect(f.input('New household name').disabled).toBe(true);
    f.element.view=current;await f.element.updateComplete;expect(f.input('New household name').value).toBe('Retained draft');
  }else expect(f.root.querySelector('form')).toBeNull();
  expect(f.intents).toEqual([]);
});
test('household-workspace-C50: closing an editor during proof refresh never focuses a removed or private control',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');f.button('Cancel').click();
  f.element.pending=true;await f.element.updateComplete;expect(f.root.querySelector('input,button')).toBeNull();expect(f.intents).toEqual([]);
  f.element.pending=false;f.element.view=current;await f.element.updateComplete;expect(f.root.activeElement).toBeNull();expect(f.root.querySelector('form')).toBeNull();
});


for(const scenario of draftFactCases)test('household-browser-C02: a different verified household retires the '+scenario.kind+' draft despite matching member/revisions',async()=>{
  const current=view(),f=await mount(current);await f.click(scenario.open);
  if(scenario.kind==='other alias')await f.change('Use Home Assistant name',false);
  await f.change(scenario.field,scenario.value);
  f.element.view={...current,capabilities:{...current.capabilities!,householdId:'replacement-home'},
    household:{...current.household!,householdId:'replacement-home'},policy:{...current.policy!,householdId:'replacement-home'}};
  await f.element.updateComplete;expect(f.root.querySelector('form')).toBeNull();expect(f.intents).toEqual([]);
  await f.click(scenario.open);expect(f.input(scenario.field).value).not.toBe(scenario.value);expect(f.intents).toEqual([]);
});
test('household-browser-C02: a detached confirmed save cannot submit the former household draft into a replacement household',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit household');await f.change('New household name','Former household intent');
  await f.click('Review changes');const save=f.button('Save changes');
  f.element.view={...current,capabilities:{...current.capabilities!,householdId:'replacement-home'},
    household:{...current.household!,householdId:'replacement-home',name:'Replacement household'},policy:{...current.policy!,householdId:'replacement-home'}};
  save.dispatchEvent(new MouseEvent('click'));expect(f.intents).toEqual([]);
  await f.element.updateComplete;save.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;
  expect(f.intents).toEqual([]);expect(f.text()).not.toContain('Former household intent');
  await f.click('Edit household');expect(f.input('New household name').value).toBe('Replacement household');
});
test('HADB-03: missing current household proof retires private drafts and makes detached controls inert until explicit reopening',async()=>{
  const current=view(),f=await mount(current);await f.click('Edit preferences');await f.change('Saved language','en');await f.click('Review changes');
  const save=f.button('Save changes');f.element.view={...current,capabilities:null};
  save.dispatchEvent(new MouseEvent('click'));expect(f.intents).toEqual([]);await f.element.updateComplete;
  save.dispatchEvent(new MouseEvent('click'));await f.element.updateComplete;expect(f.intents).toEqual([]);
  expect(f.root.querySelector('form')).toBeNull();expect(f.button('Edit preferences')).toBeUndefined();
  f.element.view=current;await f.element.updateComplete;expect(f.root.querySelector('form')).toBeNull();
  await f.click('Edit preferences');expect(f.input('Saved language').value).toBe('es');expect(f.intents).toEqual([]);
});

test('C39: the household editor reviews and submits the bounded horizon in both languages',async()=>{
  const current=view();
  const f=await mount({...current,household:{...current.household!,materializationHorizonDays:60}});
  await f.click('Edit household');
  const label='Recurrence horizon (days)';
  expect(f.input(label).value).toBe('60');
  await f.change(label,'6');await f.click('Review changes');
  expect(f.root.querySelector('[role=alert]')).not.toBeNull();
  expect(f.intents).toEqual([]);
  await f.change(label,'14');await f.click('Review changes');
  expect(f.text()).toContain('Recurrence horizon (days)14');
  await f.click('Save changes');
  expect(f.intents).toEqual([{type:'submit',command:{action:'household.update',
    payload:{expected_revision:'7',name:'Household',time_zone:'UTC',materialization_horizon_days:14}}}]);
  f.element.language='es';await f.element.updateComplete;
  expect(f.text()).toContain('Horizonte de recurrencia (días)');
});
