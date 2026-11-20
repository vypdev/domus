import {expect, test} from '@playwright/test';
import type {BrowserContext, Locator, Page} from '@playwright/test';
const prefix = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';
type Mode = 'native' | 'standalone';
const origin = (mode: Mode) => `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
const base = (mode: Mode) => origin(mode) + (mode === 'native' ? prefix : '');
async function open(page: Page, context: BrowserContext, mode: Mode) {
  if (mode === 'native') await context.addCookies([{name: 'ingress_session', value: 'f'.repeat(128), domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
  await page.goto(base(mode) + '/');
  if (mode === 'standalone') {
    await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
    await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
  }
  await page.getByLabel('Household name', {exact: true}).fill('Maple House');
  await page.getByLabel('Timezone', {exact: true}).fill('Europe/Madrid');
  await page.getByRole('button', {name: 'Create household', exact: true}).click();
  await page.getByRole('link', {name: 'Tasks', exact: true}).click();
  const tasks = page.locator('domus-tasks');
  await expect(tasks.getByRole('button', {name: 'Create task', exact: true})).toBeEnabled();
  return tasks;
}
async function saveAdministration(widget: Locator) {
  await widget.getByRole('button', {name: 'Review changes', exact: true}).click();
  await widget.getByRole('button', {name: 'Save changes', exact: true}).click();
  await expect(widget.getByRole('heading', {name: 'Original request processed', exact: true})).toBeVisible();
  await widget.getByRole('button', {name: 'Close editor', exact: true}).click();
}

for (const mode of ['native','standalone'] as const) for (const locale of ['en','es'] as const) {
  test.describe(`material workflow ${mode} ${locale}`, () => {
  test.use({hasTouch:locale==='es',viewport:{width:locale==='es'?390:1280,height:844}});
  test(`plan, review and explicitly reconcile materials in ${mode} ${locale}`, async ({page,context,request}, info) => {
    test.setTimeout(180_000);
    const t=(en:string,es:string)=>locale==='en'?en:es;
    const activate=async(control:Locator)=>{await expect(control).toBeVisible();await expect(control).toBeEnabled();
      if(locale==='es')await control.tap();else await control.press('Enter');};
    if(locale==='es') await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:locale==='es'?'dark':'light'});
    expect((await request.post(origin(mode)+'/__fixture__/reset')).ok()).toBe(true);
    const setup=page.waitForRequest(value=>value.url()===base(mode)+'/api/v1/household'&&value.method()==='POST');
    let catalogReads=0, proofReads=0;
    page.on('request',value=>{const path=new URL(value.url()).pathname;if(value.method()==='GET'&&(path.endsWith('/auth/session')||path.endsWith('/household')))proofReads++;});
    page.on('request',value=>{if(new URL(value.url()).pathname===(mode==='native'?prefix:'')+'/api/v1/inventory'&&value.method()==='GET')catalogReads++;});
    const tasks=await open(page,context,mode);
    const setupHeaders=await(await setup).allHeaders();
    const headers={'X-Domus-Context':setupHeaders['x-domus-context'],'X-CSRF-Token':setupHeaders['x-csrf-token'],Origin:origin(mode)};
    const api=base(mode)+'/api/v1/';
    const write=async(key:string,body:unknown,path='inventory/commands',method:'post'|'put'='post')=>{
      const response=await page.request[method](api+path,{headers:{...headers,'Idempotency-Key':key},data:body});
      expect(response.status(),await response.text()).toBe(200);return (await response.json()).result;
    };
    if(locale==='es')await page.getByLabel('Language',{exact:true}).selectOption('es');
    const title=tasks.getByRole('textbox',{name:t('Title','Título'),exact:true});
    await title.fill('QA 150 title only'); await activate(tasks.getByRole('button',{name:t('Create task','Crear tarea'),exact:true}));
    await expect(tasks.getByRole('heading',{name:'QA 150 title only',exact:true})).toBeVisible();
    expect(catalogReads).toBe(0);
    for(let i=0;i<28;i++)await write('material-product-'+i,{action:'inventory.register-product',name:'QA 150 product '+String(i).padStart(2,'0'),base_unit:i<2?'millilitre':'piece'});
    const firstResponse=await page.request.get(api+'inventory?limit=25',{headers}); expect(firstResponse.ok()).toBe(true);
    const first=await firstResponse.json(); expect(first.products).toHaveLength(25); expect(first.next_cursor).toBeTruthy();
    const lastResponse=await page.request.get(api+'inventory?limit=25&cursor='+encodeURIComponent(first.next_cursor),{headers}); expect(lastResponse.ok()).toBe(true);
    const last=await lastResponse.json(); expect(last.products).toHaveLength(3);
    const [used,unused]=first.products.filter((value:{base_unit:string})=>value.base_unit==='piece');
    const short=last.products[0];
    await write('initial-used',{action:'inventory.intake',product_id:used.product_id,quantity:'5'});
    await write('initial-unused',{action:'inventory.intake',product_id:unused.product_id,quantity:'5'});
    const expand=async()=>{
      const summary=tasks.getByRole('heading',{name:t('New task','Nueva tarea'),exact:true}).locator('..');
      await expect(summary).toBeVisible();
      if(!await title.isVisible())await activate(summary);
      await expect(title).toBeVisible();
    };
    await expand(); await title.fill('QA 150 material workflow');
    const description=tasks.getByRole('textbox',{name:t('Description','Descripción'),exact:true});await description.fill('Retain this draft across optional catalog failure');
    const plan=tasks.locator('domus-task-material-plan');
    await page.route(api+'inventory?limit=25',route=>route.abort('failed'),{times:1});
    await activate(plan.getByRole('button',{name:t('Add materials','Añadir materiales'),exact:true}));
    await expect(plan.getByRole('alert')).toContainText(t('could not be loaded','No se han podido cargar'));
    await expect(title).toHaveValue('QA 150 material workflow');await expect(description).toHaveValue('Retain this draft across optional catalog failure');
    await activate(plan.getByRole('button',{name:t('Refresh material choices','Actualizar materiales disponibles'),exact:true}));
    const combo=plan.getByRole('combobox',{name:t('Pantry product','Producto de Despensa'),exact:true});await expect(combo).toBeFocused();
    const choose=async(name:string)=>{await activate(combo); const option=plan.getByRole('option').filter({hasText:name});
      if(locale==='es')await option.tap();else{
        const target=await option.getAttribute('id');await combo.press('Home');
        const count=await plan.getByRole('option').count();
        for(let index=0;index<count&&await combo.getAttribute('aria-activedescendant')!==target;index++)await combo.press('ArrowDown');
        await expect(combo).toHaveAttribute('aria-activedescendant',target!);await combo.press('Enter');
      }
      await expect(plan.locator('li').last().getByText(name,{exact:true})).toBeVisible();
      await expect(plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last()).toBeFocused();};
    await choose(used.name);await plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last().fill('2');
    await activate(plan.getByRole('button',{name:t('Remove material plan','Quitar plan de materiales'),exact:true}));
    await expect(title).toHaveValue('QA 150 material workflow');
    await activate(plan.getByRole('button',{name:t('Add materials','Añadir materiales'),exact:true}));
    await choose(used.name);await plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last().fill('2');
    await choose(unused.name);await plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last().fill('2');
    await activate(plan.getByRole('button',{name:t('More products','Más productos'),exact:true}));
    await choose(short.name);await plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last().fill('2');
    await expect(plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true})).toHaveCount(3);
    await plan.screenshot({path:info.outputPath('material-plan-'+locale+'.png')});
    let creations=0,creationKey='',creationBody:Record<string,any>|null=null;
    await page.route(api+'tasks/definitions',async route=>{
      creations++;creationKey=route.request().headers()['idempotency-key'];
      const response=await route.fetch({maxRetries:0,maxRedirects:0});expect(response.status()).toBe(200);
      creationBody=await response.json();await route.abort('connectionreset');
    });
    await activate(tasks.getByRole('button',{name:t('Create task','Crear tarea'),exact:true}));
    await expect(tasks.getByRole('heading',{name:t('Result not confirmed','Resultado sin confirmar'),exact:true})).toBeVisible();
    await page.unroute(api+'tasks/definitions');await page.reload();
    await expect(tasks.getByRole('button',{name:'QA 150 material workflow',exact:true})).toBeVisible();
    if(locale==='es')await page.getByLabel('Language',{exact:true}).selectOption('es');
    const originals:Record<string,any>[]=[];
    await page.route(api+'tasks/requests/task.create/'+creationKey,async route=>{const response=await route.fetch({maxRetries:0,maxRedirects:0});
      expect(response.status()).toBe(200);originals.push(await response.json());await route.fulfill({response});});
    await activate(tasks.getByRole('button',{name:t('Check saved request','Comprobar solicitud guardada'),exact:true}).first());
    await expect(tasks.getByRole('heading',{name:'QA 150 material workflow',exact:true})).toBeVisible();
    expect(creations).toBe(1);expect(originals).toHaveLength(1);expect(originals[0].operation_id).toBe(creationBody!.operation_id);
    const oid=creationBody!.result.occurrence_id;
    await tasks.getByLabel(used.name,{exact:true}).fill('1');await tasks.getByLabel(unused.name,{exact:true}).fill('0');await tasks.getByLabel(short.name,{exact:true}).fill('1');
    await activate(tasks.getByRole('button',{name:t('Mark done now','Marcar como hecha ahora'),exact:true}));
    let outcomes=tasks.locator('domus-task-material-outcomes').first();
    await expect(outcomes.getByRole('status').filter({hasText:new RegExp('^'+t('Consumption confirmed','Consumo contabilizado')+'$')})).toBeVisible();
    await expect(outcomes.getByText(t('Not used · no stock movement','Sin utilizar · sin movimiento de existencias'),{exact:true})).toBeVisible();
    await expect(outcomes.getByText(t('Inventory review required','Requiere revisión de Inventario'),{exact:true})).toBeVisible();
    for(const colorScheme of ['light','dark'] as const){await page.emulateMedia({colorScheme});await outcomes.screenshot({path:info.outputPath('material-outcomes-'+locale+'-'+colorScheme+'.png')});}
    const readWork=async()=>{const response=await page.request.get(api+'tasks/occurrences/'+oid,{headers});expect(response.ok()).toBe(true);return response.json();};
    const before=await readWork(), firstPending=before.materials.find((value:{state:string})=>value.state==='pending_regularization');
    expect(before.work.state).toBe('completed');expect(before.materials.map((value:{state:string})=>value.state).sort()).toEqual(['not_used','pending_regularization','posted']);
    const reopen=async(reason:string)=>{
      await tasks.getByLabel(t('Reason','Motivo'),{exact:true}).fill(reason);
      await activate(tasks.getByRole('button',{name:t('Reopen task','Reabrir tarea'),exact:true}));
      await expect(tasks.getByRole('button',{name:t('Mark done now','Marcar como hecha ahora'),exact:true})).toBeVisible();
    };
    await reopen('QA 150 retain the first pending completion');
    await tasks.getByLabel(used.name,{exact:true}).fill('0');await tasks.getByLabel(unused.name,{exact:true}).fill('0');await tasks.getByLabel(short.name,{exact:true}).fill('1');
    await activate(tasks.getByRole('button',{name:t('Mark done now','Marcar como hecha ahora'),exact:true}));
    await expect(outcomes.getByText(t('Inventory review required','Requiere revisión de Inventario'),{exact:true})).toBeVisible();
    const second=await readWork(), secondPending=second.materials.find((value:{state:string})=>value.state==='pending_regularization');
    expect(second.cycle.cycle_id).not.toBe(before.cycle.cycle_id);expect(secondPending.intent_id).not.toBe(firstPending.intent_id);
    await reopen('QA 150 retain the second pending completion');
    const reopened=await readWork();expect(reopened.work.state).toBe('available');expect(reopened.cycle).toBeNull();expect(reopened.materials).toEqual([]);
    await write('refill-shortfall',{action:'inventory.intake',product_id:short.product_id,quantity:'5'});
    await activate(tasks.getByRole('button',{name:t('Review earlier usage','Revisar consumos anteriores'),exact:true}));
    await expect(tasks.getByRole('heading',{name:t('Earlier material usage','Consumos anteriores'),exact:true})).toBeFocused();
    outcomes=tasks.locator('#material-history-heading').locator('..').locator('domus-task-material-outcomes');
    await expect(outcomes.getByText(t('Inventory review required','Requiere revisión de Inventario'),{exact:true})).toBeVisible();
    const pageResponse=await page.request.get(api+'tasks/occurrences/'+oid+'/material-history?limit=1',{headers});expect(pageResponse.ok()).toBe(true);
    const firstPage=await pageResponse.json();expect(firstPage.items).toHaveLength(1);expect(firstPage.next_cursor).toBeTruthy();
    const pending=firstPage.items[0].materials.find((value:{state:string})=>value.state==='pending_regularization');
    expect([firstPending.intent_id,secondPending.intent_id]).toContain(pending.intent_id);
    const postedBefore=firstPage.items[0].materials.filter((value:{state:string})=>value.state==='posted').length;
    await tasks.locator('#material-history-heading').locator('..').screenshot({path:info.outputPath('closed-material-usage-'+locale+'.png')});
    let settlements=0,settlementKey='',settlementBody:Record<string,any>|null=null;
    await page.route(api+'tasks/occurrences/'+oid+'/materials/'+pending.intent_id+'/settlement',async route=>{
      settlements++;settlementKey=route.request().headers()['idempotency-key'];expect(route.request().postDataJSON().expected_revision).toBe(pending.revision);
      const response=await route.fetch({maxRetries:0,maxRedirects:0});expect(response.status()).toBe(200);settlementBody=await response.json();await route.abort('connectionreset');});
    await activate(outcomes.getByRole('button',{name:t('Settle pending usage','Contabilizar consumo pendiente'),exact:true}));
    await expect(tasks.getByRole('heading',{name:t('Result not confirmed','Resultado sin confirmar'),exact:true})).toBeVisible();
    const settlementOriginals:Record<string,any>[]=[];
    await page.route(api+'tasks/requests/task.material.settle/'+settlementKey,async route=>{const response=await route.fetch({maxRetries:0,maxRedirects:0});
      expect(response.status()).toBe(200);settlementOriginals.push(await response.json());await route.fulfill({response});});
    await activate(tasks.getByRole('button',{name:t('Check saved request','Comprobar solicitud guardada'),exact:true}).first());
    await expect(outcomes.getByRole('status').filter({hasText:new RegExp('^'+t('Consumption confirmed','Consumo contabilizado')+'$')})).toHaveCount(postedBefore+1);
    expect(settlements).toBe(1);expect(settlementOriginals).toHaveLength(1);expect(settlementOriginals[0].operation_id).toBe(settlementBody!.operation_id);
    expect(await readWork()).toEqual(reopened);
    const historyResponse=await page.request.get(api+'tasks/occurrences/'+oid+'/materials?cycle_id='+pending.cycle_id,{headers});expect(historyResponse.ok()).toBe(true);
    const history=await historyResponse.json();expect(history.cycle.cycle_id).toBe(pending.cycle_id);expect(history.cycle.closed_at).not.toBeNull();
    expect(history.materials.find((value:{intent_id:string})=>value.intent_id===pending.intent_id)).toMatchObject({line_id:pending.line_id,confirmed_quantity:'1',movement_id:settlementBody!.result.material.movement_id});
    const moreHistory=tasks.getByRole('button',{name:t('Next closed completion','Siguiente realización cerrada'),exact:true});
    await expect(moreHistory).toBeVisible();
    await tasks.locator('#material-history-heading').locator('..').screenshot({path:info.outputPath('recovered-material-continuation-'+locale+'.png')});
    await activate(moreHistory);
    await expect(outcomes.getByText(t('Inventory review required','Requiere revisión de Inventario'),{exact:true})).toBeVisible();
    const laterResponse=await page.request.get(api+'tasks/occurrences/'+oid+'/material-history?limit=1&cursor='+encodeURIComponent(firstPage.next_cursor),{headers});expect(laterResponse.ok()).toBe(true);
    const laterPage=await laterResponse.json();expect(laterPage.items).toHaveLength(1);expect(laterPage.next_cursor).toBeNull();
    const laterPending=laterPage.items[0].materials.find((value:{state:string})=>value.state==='pending_regularization');
    expect(laterPending.intent_id).not.toBe(pending.intent_id);
    expect(new Set([pending.cycle_id,laterPending.cycle_id])).toEqual(new Set([before.cycle.cycle_id,second.cycle.cycle_id]));
    const laterPosted=laterPage.items[0].materials.filter((value:{state:string})=>value.state==='posted').length;
    let laterSends=0,laterBody:Record<string,any>|null=null;
    await page.route(api+'tasks/occurrences/'+oid+'/materials/'+laterPending.intent_id+'/settlement',async route=>{
      laterSends++;const response=await route.fetch({maxRetries:0,maxRedirects:0});expect(response.status()).toBe(200);laterBody=await response.json();await route.fulfill({response});});
    await activate(outcomes.getByRole('button',{name:t('Settle pending usage','Contabilizar consumo pendiente'),exact:true}));
    await expect(outcomes.getByRole('status').filter({hasText:new RegExp('^'+t('Consumption confirmed','Consumo contabilizado')+'$')})).toHaveCount(laterPosted+1);
    expect(laterSends).toBe(1);expect(laterBody!.result.material.movement_id).not.toBe(settlementBody!.result.material.movement_id);expect(await readWork()).toEqual(reopened);
    await tasks.locator('#material-history-heading').locator('..').screenshot({path:info.outputPath('second-closed-material-settled-'+locale+'.png')});
    await info.attach('creation-original',{body:JSON.stringify({committed:creationBody,original:originals[0]}),contentType:'application/json'});
    await info.attach('settlement-original',{body:JSON.stringify({committed:settlementBody,original:settlementOriginals[0]}),contentType:'application/json'});
    await info.attach('closed-material-pages',{body:JSON.stringify({firstPage,laterPage,laterBody}),contentType:'application/json'});
    // Explicitly retire three resolved originals; unconfirmed entries are never evicted.
    const dismiss=tasks.getByRole('button',{name:t('Dismiss saved request','Descartar solicitud guardada'),exact:true});
    const savedRequests=tasks.locator('summary').filter({hasText:new RegExp('^'+t('Saved requests','Solicitudes guardadas')+'$')});
    for(let index=0;index<3;index++){
      await activate(tasks.getByRole('button',{name:t('Refresh tasks','Actualizar tareas'),exact:true}));
      await activate(savedRequests);await expect(dismiss).toHaveCount(8-index);await activate(dismiss.first());
    }
    await activate(tasks.getByRole('button',{name:t('Refresh tasks','Actualizar tareas'),exact:true}));
    await activate(savedRequests);await expect(dismiss).toHaveCount(5);
    outcomes=tasks.locator('domus-task-material-outcomes').first();
    const policyReply=await page.request.get(api+'tasks/policy',{headers}), policy=await policyReply.json();
    await write('separate-recording-policy',{expected_revision:policy.revision,rules:{...policy.rules,material_recording:'separate_recording'}},'tasks/policy','put');
    await expand();await title.fill('QA 150 missing actual quantity');
    await activate(plan.getByRole('button',{name:t('Add materials','Añadir materiales'),exact:true}));await choose(used.name);
    await activate(tasks.getByRole('button',{name:t('Create task','Crear tarea'),exact:true}));
    await expect(tasks.getByRole('heading',{name:'QA 150 missing actual quantity',exact:true})).toBeVisible();
    await activate(tasks.getByRole('button',{name:t('Mark done now','Marcar como hecha ahora'),exact:true}));
    await expect(outcomes.getByText(t('Actual quantity not recorded','Cantidad utilizada sin registrar'),{exact:true})).toBeVisible();
    await outcomes.getByRole('textbox',{name:t('Actual quantity','Cantidad utilizada'),exact:true}).fill('0');
    await outcomes.getByRole('textbox',{name:t('Reason for recording','Motivo del registro'),exact:true}).fill('QA 150 nothing used');
    await activate(outcomes.getByRole('button',{name:t('Record actual usage','Registrar consumo real'),exact:true}));
    await expect(outcomes.getByText(t('Not used · no stock movement','Sin utilizar · sin movimiento de existencias'),{exact:true})).toBeVisible();
    await expect(outcomes.getByRole('button',{name:t('Settle pending usage','Contabilizar consumo pendiente'),exact:true})).toHaveCount(0);
    await outcomes.screenshot({path:info.outputPath('material-zero-recorded-'+locale+'.png')});
    const scheduled:Record<string,any>[]=[];
    for(const kind of ['fixed','relative'] as const){
      await expand();await title.fill('QA 150 '+kind+' material plan');
      await activate(plan.getByRole('button',{name:t('Add materials','Añadir materiales'),exact:true}));
      const decimal=[...first.products,...last.products].find((value:{base_unit:string})=>value.base_unit==='millilitre');
      const product=kind==='fixed'?used:decimal;
      if(!first.products.some((value:{product_id:string})=>value.product_id===product.product_id))await activate(plan.getByRole('button',{name:t('More products','Más productos'),exact:true}));
      await choose(product.name);
      const quantityField=plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true}).last();
      const field=await quantityField.elementHandle(), reads=proofReads;
      await quantityField.fill('');
      await quantityField.pressSequentially(kind==='fixed'?'2':locale==='es'?'1,25':'1.25');
      await expect(quantityField).toBeFocused();
      expect(await quantityField.evaluate((current,original)=>current===original,field)).toBe(true);
      expect(proofReads).toBe(reads);
      await tasks.getByRole('combobox',{name:t('Scheduling','Programación'),exact:true}).selectOption(kind);
      await tasks.getByLabel(t('First date','Primera fecha'),{exact:true}).fill(new Date(Date.now()+30*86_400_000).toISOString().slice(0,10));
      if(kind==='fixed')await tasks.getByLabel(t('Recurrence rule','Regla de recurrencia'),{exact:true}).fill('FREQ=DAILY;COUNT=2');
      const path=api+'tasks/recurrence/creation/'+kind;
      await page.route(path,async route=>{const response=await route.fetch({maxRetries:0,maxRedirects:0});expect(response.status()).toBe(200);scheduled.push(await response.json());await route.fulfill({response});});
      const create=tasks.getByRole('button',{name:t('Create task','Crear tarea'),exact:true});
      {
        // The added reopening fills the eight-record journal before either scheduled creation.
        await activate(create);await expect(tasks.getByRole('alert')).toContainText(t('make room','espacio'));
        await expect(title).toHaveValue('QA 150 '+kind+' material plan');
        await expect(plan.getByRole('textbox',{name:t('Planned quantity','Cantidad prevista'),exact:true})).toHaveValue(kind==='fixed'?'2':locale==='es'?'1,25':'1.25');
        if(!await tasks.getByRole('button',{name:t('Dismiss saved request','Descartar solicitud guardada'),exact:true}).first().isVisible()) await activate(tasks.locator('summary').filter({hasText:new RegExp('^'+t('Saved requests','Solicitudes guardadas')+'$')}));
        await activate(tasks.getByRole('button',{name:t('Dismiss saved request','Descartar solicitud guardada'),exact:true}).first());
      }
      let failedPostCreateReads=0;
      if(kind==='fixed')await page.route(api+'tasks/occurrences?limit=25',route=>{
        failedPostCreateReads++;return route.abort('failed');
      },{times:1});
      await activate(create);
      await expect.poll(()=>scheduled.length).toBe(kind==='fixed'?1:2);
      await expect(tasks.getByText(t('The schedule was saved. Its first task will appear when recurrence processing runs.',
        'Se ha guardado la programación. La primera tarea aparecerá cuando se procese la recurrencia.'),{exact:true})).toBeVisible();
      await expect(title).not.toBeVisible();
      const receipt=scheduled.at(-1)!;
      const definition=await page.request.get(api+'tasks/definitions/'+receipt.result.definition_id,{headers});expect(definition.ok()).toBe(true);
      const saved=await definition.json();expect(saved.materials).toHaveLength(1);expect(saved.materials[0]).toMatchObject({planned_quantity:kind==='fixed'?'2':'1.25',binding:{reference_id:product.reference_id,unit_id:product.base_unit,location_id:'pantry'}});
      await page.unroute(path);
      if(kind==='fixed'){
        await expect.poll(()=>failedPostCreateReads).toBe(1);
        await expect(tasks.getByRole('alert')).toContainText(t('Tasks could not be loaded','No se han podido cargar las tareas'));
        await expect(tasks.getByRole('button',{name:t('Refresh tasks','Actualizar tareas'),exact:true})).toBeFocused();
        await expect(tasks.getByRole('button',{name:t('Refresh tasks','Actualizar tareas'),exact:true})).toBeInViewport();
        await page.screenshot({path:info.outputPath('post-create-read-recovery-'+locale+'.png')});
        await expand();await expect(title).toHaveValue('');await expect(plan.locator('li')).toHaveCount(0);
        await expect(plan.getByRole('button',{name:t('Add materials','Añadir materiales'),exact:true})).toBeVisible();
        await plan.screenshot({path:info.outputPath('committed-plan-retired-after-read-failure-'+locale+'.png')});
        await activate(tasks.getByRole('button',{name:t('Refresh tasks','Actualizar tareas'),exact:true}));
      }
    }
    await info.attach('scheduled-material-originals',{body:JSON.stringify(scheduled),contentType:'application/json'});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
  });
}
for (const mode of ['native', 'standalone'] as const) {
  for (const locale of ['en', 'es'] as const) {
    test(`category recovery, filter and stale draft in ${mode} ${locale}`, async ({page, context, request}) => {
      expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
      const tasks = await open(page, context, mode);
      const t = (english: string, spanish: string) => locale === 'en' ? english : spanish;
      const language = page.getByLabel('Language', {exact: true});
      if (locale === 'es') await language.selectOption('es');
      await page.setViewportSize({width: 320, height: 720});
      const manager = tasks.getByRole('heading', {name: t('Task categories', 'Categorías de tareas'), exact: true});
      const categoryName = tasks.getByRole('textbox', {name: t('Category name', 'Nombre de la categoría')});
      const expand = async () => {if (!await categoryName.isVisible()) await manager.click();};
      await manager.locator('..').focus();
      await page.keyboard.press('Enter');
      await expect(categoryName).toBeVisible();
      const label = '<b>Garden 🌿</b>', updated = 'Garden renamed';
      await categoryName.fill(label);
      let creates = 0;
      let originalKey = '';
      await page.route(base(mode) + '/api/v1/tasks/categories', async route => {
        expect(route.request().method()).toBe('POST');
        creates++;
        originalKey = route.request().headers()['idempotency-key'];
        const committed = await route.fetch({maxRetries: 0, maxRedirects: 0});
        expect(committed.status()).toBe(200);
        await route.abort('connectionreset');
      });
      await tasks.getByRole('button', {name: t('Create category', 'Crear categoría'), exact: true}).click();
      await expect(tasks.getByRole('heading', {name: t('Result not confirmed', 'Resultado sin confirmar')})).toBeVisible();
      const original = page.waitForResponse(response => response.url().endsWith('/task.category.create/' + originalKey));
      await tasks.getByRole('button', {name: t('Check saved request', 'Comprobar solicitud guardada'), exact: true}).first().click();
      expect((await original).ok()).toBe(true);
      expect(creates).toBe(1);
      await page.unroute(base(mode) + '/api/v1/tasks/categories');
      const choice = tasks.getByRole('combobox', {name: t('Category', 'Categoría'), exact: true});
      await expect(choice).toBeVisible();
      const categoryId = await choice.locator('option', {hasText: label}).getAttribute('value');
      expect(categoryId).toBeTruthy();
      expect(categoryId).not.toBe(label);
      await expect(choice.locator('option').first()).toHaveText(t('Unclassified', 'Sin categoría'));
      await choice.selectOption(categoryId!);
      const title = tasks.getByRole('textbox', {name: t('Title', 'Título'), exact: true});
      await title.fill('Classified work');
      await tasks.getByRole('button', {name: t('Create task', 'Crear tarea'), exact: true}).click();
      await expect(tasks.getByRole('heading', {name: 'Classified work', exact: true})).toBeVisible();
      await expect(tasks.getByText(t('Category ', 'Categoría ') + label, {exact: true})).toBeVisible();
      await expect(tasks.locator('b')).toHaveCount(0);
      await tasks.getByRole('button', {name: t('Mark done now', 'Marcar como hecha ahora'), exact: true}).click();
      await expect(tasks.getByText(t('No approval required', 'No necesita aprobación'), {exact: true})).toBeVisible();

      await expand();
      const edit = tasks.getByRole('combobox', {name: t('Category to edit', 'Categoría que editar')});
      await edit.selectOption(categoryId!);
      await categoryName.fill(updated);
      await tasks.getByRole('button', {name: t('Rename category', 'Renombrar categoría'), exact: true}).click();
      await expect(tasks.locator('#manage-task-category option', {hasText: updated})).toHaveCount(1);
      await page.getByRole('link', {name: t('Calendar', 'Calendario'), exact: true}).click();
      const calendar = page.locator('domus-calendar');
      const filter = calendar.getByRole('combobox', {name: t('Category', 'Categoría'), exact: true});
      await filter.selectOption(categoryId!);
      const filtered = page.waitForResponse(response => new URL(response.url()).searchParams.get('category') === categoryId);
      await calendar.getByRole('button', {name: t('Show calendar', 'Mostrar calendario'), exact: true}).click();
      expect((await filtered).ok()).toBe(true);
      await expect(calendar.getByText(t('Matching entries 1. Matching tasks 1', 'Entradas que coinciden 1. Tareas que coinciden 1'))).toBeVisible();
      await expect(calendar.getByText(t('Category ', 'Categoría ') + label, {exact: true})).toBeVisible();

      await page.getByRole('link', {name: t('Tasks', 'Tareas'), exact: true}).click();
      if (!await title.isVisible()) await tasks.getByRole('heading', {name: t('New task', 'Nueva tarea'), exact: true}).click();
      await title.fill('Keep this title');
      const description = tasks.getByRole('textbox', {name: t('Description', 'Descripción')});
      await description.fill('Keep this description');
      await tasks.getByRole('combobox', {name:t('Scheduling', 'Programación'), exact:true}).selectOption('fixed');
      const scheduleDate = tasks.getByLabel(t('First date', 'Primera fecha'), {exact:true});
      const scheduleRule = tasks.getByLabel(t('Recurrence rule', 'Regla de recurrencia'), {exact:true});
      const localDate = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
      await scheduleDate.fill(localDate);
      await scheduleRule.fill('FREQ=WEEKLY');
      await choice.selectOption(categoryId!);
      await expand();
      await edit.selectOption(categoryId!);
      const originalArchive = page.waitForRequest(request => request.url().endsWith('/' + categoryId + '/archive'));
      await tasks.getByRole('button', {name: t('Archive category', 'Archivar categoría'), exact: true}).click();
      const authorization = await (await originalArchive).allHeaders();
      await expect(choice).toHaveAttribute('aria-invalid', 'true');
      await expect(title).toHaveValue('Keep this title');
      await expect(description).toHaveValue('Keep this description');
      await expect(scheduleDate).toHaveValue(localDate);
      await expect(scheduleRule).toHaveValue('FREQ=WEEKLY');
      await expect(tasks.getByRole('button', {name: t('Create task', 'Crear tarea'), exact: true})).toBeDisabled();
      await choice.selectOption('');
      await tasks.getByRole('combobox', {name:t('Scheduling', 'Programación'), exact:true}).selectOption('manual');
      await tasks.getByRole('button', {name: t('Create task', 'Crear tarea'), exact: true}).click();
      await expect(tasks.getByRole('heading', {name: 'Keep this title', exact: true})).toBeVisible();
      await expand();
      await edit.selectOption('');
      await categoryName.fill('Concurrent archive');
      await tasks.getByRole('button', {name: t('Create category', 'Crear categoría'), exact: true}).click();
      const activeCategory = tasks.locator('#manage-task-category option', {hasText: 'Concurrent archive'});
      await expect(activeCategory).toHaveCount(1);
      const activeId = (await activeCategory.getAttribute('value'))!;
      await page.getByRole('link', {name: t('Calendar', 'Calendario'), exact: true}).click();
      const show = calendar.getByRole('button', {name: t('Show calendar', 'Mostrar calendario'), exact: true});
      await filter.selectOption(activeId);
      const archive = await page.request.post(base(mode) + '/api/v1/tasks/categories/' + activeId + '/archive', {
        headers: {'X-Domus-Context': authorization['x-domus-context'], 'X-CSRF-Token': authorization['x-csrf-token'],
          'Idempotency-Key': 'concurrent-calendar-category-archive', Origin: origin(mode)},
        data: {expected_revision: 1},
      });
      expect(archive.status()).toBe(200);
      await show.click();
      await expect(filter).toHaveAttribute('aria-invalid', 'true');
      await expect(calendar.getByRole('alert')).toHaveText(t('Choose an active category or clear the filter.',
        'Elige una categoría activa o quita el filtro.'));
      await expect(show).toBeDisabled();
      await filter.selectOption('');
      const allEntries = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname.endsWith('/api/v1/tasks/calendar') && !url.searchParams.has('category');
      });
      await show.click();
      expect((await allEntries).ok()).toBe(true);
      await expect(filter.locator('option').filter({hasText: 'Concurrent archive'})).toHaveCount(0);
      await expect(calendar.getByText(t('Category ', 'Categoría ') + label, {exact: true})).toBeVisible();
    });
  }
}

for (const mode of ['native', 'standalone'] as const) test.describe('tasks ' + mode, () => {
  test.beforeEach(async ({request}) => {
    if (process.env.DOMUS_BROWSER_IMAGE) {
      const image = await request.get(origin(mode) + '/__fixture__/image');
      expect(image.status()).toBe(200);
      expect(await image.json()).toEqual({source_commit: process.env.DOMUS_TEST_SOURCE_COMMIT, architecture: process.env.DOMUS_TEST_ARCH,
        image_id: expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode});
    }
    expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
  });
  for (const locale of ['en', 'es'] as const) test('actual UI creates, claims, completes and reloads SQLite work in ' + locale, async ({page, context}) => {
    const tasks = await open(page, context, mode), spanish = locale === 'es';
    if (spanish) await page.getByLabel('Language', {exact: true}).selectOption('es');
    const title = spanish ? 'Limpiar la mesa 🧹 <script>literal</script>' : 'Clean the table 🧹 <script>literal</script>';
    await tasks.getByLabel(spanish ? 'Título' : 'Title', {exact: true}).fill(title);
    await tasks.getByLabel(spanish ? 'Descripción' : 'Description', {exact: true}).fill('Wipe then dry.');
    await tasks.getByRole('button', {name: spanish ? 'Crear tarea' : 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: title, exact: true})).toBeVisible();
    await expect(tasks.locator('script,img')).toHaveCount(0);
    await tasks.getByRole('button', {name: spanish ? 'Quedarme esta tarea' : 'Claim task', exact: true}).click();
    await expect(tasks.getByRole('button', {name: spanish ? 'Marcar como hecha ahora' : 'Mark done now', exact: true})).toBeEnabled();
    await tasks.getByRole('button', {name: spanish ? 'Marcar como hecha ahora' : 'Mark done now', exact: true}).click();
    await expect(tasks.getByText(spanish ? 'No necesita aprobación' : 'No approval required', {exact: true})).toBeVisible();
    const pageOfWork = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json();
    expect(pageOfWork.items).toHaveLength(1); expect(pageOfWork.items[0]).toMatchObject({title, state: 'completed', revision: 3});
    const actual = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences/' + pageOfWork.items[0].occurrence_id)).json();
    expect(actual.cycle.performers).toHaveLength(1); expect(actual.cycle.verification).toBe('none'); expect(actual.consumer_delivery).toBe('unconfirmed');
    await page.getByRole('link', {name: spanish ? 'Calendario' : 'Calendar', exact: true}).click();
    const calendar = page.locator('domus-calendar');
    await calendar.getByRole('combobox', {name: spanish ? 'Vista del calendario' : 'Calendar view', exact: true}).selectOption('day');
    await calendar.getByRole('combobox', {name: spanish ? 'Tipo de entrada' : 'Entry kind', exact: true}).selectOption('performed');
    await calendar.getByLabel(spanish ? 'Solo mis entradas' : 'Only my entries', {exact: true}).check();
    await calendar.getByRole('button', {name: spanish ? 'Mostrar calendario' : 'Show calendar', exact: true}).click();
    const performed = calendar.locator('.calendar-entries li').filter({hasText: title});
    await expect(performed).toHaveCount(1);
    await expect(performed).toContainText(spanish ? 'Realizado' : 'Performed');
    await expect(performed.locator('time')).toBeVisible();
    await expect(calendar.locator('script,img')).toHaveCount(0);
    await page.getByRole('link', {name: spanish ? 'Tareas' : 'Tasks', exact: true}).click();
    await page.reload(); await expect(tasks.getByRole('button', {name: title, exact: true})).toBeVisible();
    await tasks.getByRole('button', {name: title, exact: true}).click();
    await expect(tasks.getByText('No approval required', {exact: true})).toBeVisible();
    const stats = await (await page.request.get(origin(mode) + '/__fixture__/stats')).json(); expect(stats.counts.receipts).toBe(4);
    if (mode === 'native' && !spanish) await page.screenshot({path: 'test-results/tasks-native-completed.png', fullPage: true});
    if (spanish) await page.getByLabel('Language', {exact: true}).selectOption('es');
    const manual = spanish ? 'Revisar el filtro' : 'Check the filter';
    const manualTitle = tasks.getByLabel(spanish ? 'Título' : 'Title', {exact: true});
    if (!await manualTitle.isVisible())
      await tasks.getByRole('heading', {name: spanish ? 'Nueva tarea' : 'New task', exact: true}).click();
    await manualTitle.fill(manual);
    await tasks.getByRole('button', {name: spanish ? 'Crear tarea' : 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: manual, exact: true})).toBeVisible();
    const review = page.locator('domus-recurrence-review');
    await review.getByRole('button', {name: spanish ? 'Revisar programación' : 'Review scheduling', exact: true}).click();
    const localDate = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
    await review.getByLabel(spanish ? 'Fecha local' : 'Local date', {exact: true}).fill(localDate);
    await review.getByRole('button', {name: spanish ? 'Previsualizar cambio de programación' : 'Preview schedule change', exact: true}).click();
    await expect(review.getByText(localDate, {exact: false})).toBeVisible();
    let applications = 0;
    await page.route(base(mode) + '/api/v1/tasks/recurrence/reviews/attachment/apply', async route => {
      applications++;
      const committed = await route.fetch({maxRetries: 0, maxRedirects: 0});
      expect(committed.status()).toBe(200);
      await route.abort('connectionreset');
    });
    await review.getByRole('button', {name: spanish ? 'Aplicar cambio revisado' : 'Apply reviewed change', exact: true}).click();
    await expect(review.getByRole('alert')).toContainText(spanish ? 'El resultado no está confirmado' : 'The result is unconfirmed');
    await page.reload();
    await review.getByRole('button', {name: 'Check original schedule request', exact: true}).last().click();
    await expect(review.getByRole('heading', {name: 'Schedule change saved', exact: true})).toBeVisible();
    expect(applications).toBe(1);
    const retained = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json();
    expect(retained.items.filter((item: {title: string}) => item.title === manual)).toHaveLength(1);

    if (spanish) await page.getByLabel('Language', {exact: true}).selectOption('es');
    const plannedTitle = tasks.getByLabel(spanish ? 'Título' : 'Title', {exact: true});
    if (!await plannedTitle.isVisible())
      await tasks.getByRole('heading', {name: spanish ? 'Nueva tarea' : 'New task', exact: true}).click();
    await plannedTitle.fill('Recurring inspection');
    const kind = spanish ? 'relative' : 'fixed';
    await tasks.getByLabel(spanish ? 'Programación' : 'Scheduling', {exact: true}).selectOption(kind);
    await tasks.getByLabel(spanish ? 'Primera fecha' : 'First date', {exact: true}).fill(localDate);
    if (spanish) {
      await tasks.getByLabel('Días locales entre tareas', {exact: true}).fill('18');
      await tasks.getByLabel('Generar la siguiente tarea', {exact: true}).selectOption('at_verification');
    } else {
      await tasks.getByLabel('Recurrence rule', {exact: true}).fill('FREQ=DAILY;COUNT=2');
    }
    let creations = 0;
    await page.route(base(mode) + '/api/v1/tasks/recurrence/creation/' + kind, async route => {
      creations++;
      const committed = await route.fetch({maxRetries: 0, maxRedirects: 0});
      expect(committed.status()).toBe(200);
      await route.abort('connectionreset');
    });
    await tasks.getByRole('button', {name: spanish ? 'Crear tarea' : 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: spanish ? 'Resultado sin confirmar' : 'Result not confirmed', exact: true})).toBeVisible();
    await page.reload();
    await tasks.getByRole('button', {name: 'Check saved request', exact: true}).first().click();
    await expect(tasks.getByText('The schedule was saved. Its first task will appear when recurrence processing runs.', {exact: true})).toBeVisible();
    expect(creations).toBe(1);
  });
  test('a restricted member claims and performs work; an adult approves and reopens its retained cycle', async ({page, context, browser, request}) => {
    const tasks = await open(page, context, mode), title = 'Kitchen responsibility';
    await tasks.getByLabel('Title', {exact: true}).fill(title); await tasks.getByRole('button', {name: 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: title, exact: true})).toBeVisible();
    await page.getByRole('link', {name: 'Household', exact: true}).click(); const administration = page.locator('domus-administration');
    await administration.getByRole('button', {name: 'Edit access rules', exact: true}).click();
    await administration.getByLabel('HA administrator mapping', {exact: true}).selectOption('selected_ha_user');
    await administration.getByLabel('Target Home Assistant account', {exact: true}).selectOption('a'.repeat(32)); await saveAdministration(administration);
    const peer = await browser.newContext(), participant = await peer.newPage(), subject = mode === 'native' ? 'c' : 'b';
    try {
      if (mode === 'native') await peer.addCookies([{name: 'ingress_session', value: 'e'.repeat(128), domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
      else expect((await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: subject.repeat(32)}})).ok()).toBe(true);
      await participant.goto(base(mode) + '/');
      if (mode === 'standalone') {
        await participant.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
        await participant.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
      }
      await participant.getByRole('button', {name: 'Request membership', exact: true}).click();
      await expect(participant.getByRole('heading', {name: 'Membership pending', exact: true})).toBeVisible();
      if (mode === 'standalone') await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'a'.repeat(32)}});
      await administration.getByRole('button', {name: 'Refresh administration', exact: true}).click();
      await administration.getByRole('button', {name: 'Manage participant: Fictional account ' + subject, exact: true}).click();
      await expect(administration.getByLabel('Household profile', {exact: true})).toHaveValue('restricted');
      await administration.getByLabel('Membership status', {exact: true}).selectOption('active');
      await administration.getByRole('button', {name: 'Review changes', exact: true}).click();
      await administration.getByRole('checkbox', {name: 'Approve household access', exact: true}).check();
      await administration.getByRole('button', {name: 'Review changes', exact: true}).click();
      await administration.getByRole('button', {name: 'Save changes', exact: true}).click();
      await expect(administration.getByRole('heading', {name: 'Original request processed', exact: true})).toBeVisible();
      await administration.getByRole('button', {name: 'Close editor', exact: true}).click();
      await participant.getByRole('button', {name: 'Refresh status', exact: true}).click();
      await participant.getByRole('link', {name: 'Tasks', exact: true}).click();
      const memberTasks = participant.locator('domus-tasks'); await memberTasks.getByRole('button', {name: title, exact: true}).click();
      await expect(memberTasks.getByRole('button', {name: 'Create task', exact: true})).toHaveCount(0);
      await expect(memberTasks.getByRole('button', {name: 'Change assignment', exact: true})).toHaveCount(0);
      await memberTasks.getByRole('button', {name: 'Claim task', exact: true}).click();
      await memberTasks.locator('summary').filter({hasText: 'Saved requests'}).click();
      await memberTasks.getByRole('button', {name: 'Dismiss saved request', exact: true}).click();

      await page.getByRole('link', {name: 'Tasks', exact: true}).click();
      await tasks.getByRole('button', {name: 'Refresh tasks', exact: true}).click();
      await tasks.getByRole('button', {name: title, exact: true}).click();
      const allocation = tasks.locator('domus-allocation-settings');
      await allocation.getByRole('combobox', {name: 'Policy', exact: true}).selectOption('manual');
      await allocation.getByRole('button', {name: 'Save policy', exact: true}).click();
      await expect(allocation.getByText('Points policy saved.', {exact: true})).toBeVisible();
      await memberTasks.getByRole('button', {name: 'Refresh tasks', exact: true}).click();
      await expect(memberTasks.getByText(/Ask a points administrator to record this work/u)).toBeVisible();
      await expect(memberTasks.getByRole('button', {name: 'Mark done now', exact: true})).toHaveCount(0);
      await participant.getByLabel('Language', {exact: true}).selectOption('es');
      await expect(memberTasks.getByText(/Pide a un administrador de puntos/u)).toBeVisible();
      await participant.getByLabel('Idioma', {exact: true}).selectOption('en');
      await allocation.getByRole('button', {name: 'Use household default', exact: true}).click();
      await expect(allocation.getByText('This task uses the household default.', {exact: true})).toBeVisible();
      await memberTasks.getByRole('button', {name: 'Refresh tasks', exact: true}).click();

      let completionWrites = 0;
      await participant.route(base(mode) + '/api/v1/tasks/occurrences/*/complete', async route => {
        completionWrites++; const upstream = await route.fetch({maxRetries: 0, maxRedirects: 0}); expect(upstream.status()).toBe(200);
        await route.abort('connectionreset');
      });
      await memberTasks.getByRole('button', {name: 'Mark done now', exact: true}).click();
      await expect(memberTasks.getByRole('heading', {name: 'Result not confirmed', exact: true})).toBeVisible();
      await participant.reload(); await memberTasks.getByRole('button', {name: 'Check saved request', exact: true}).click();
      await expect(memberTasks.getByRole('heading', {name: 'Task change saved', exact: true})).toBeVisible();
      expect(completionWrites).toBe(1);
      await expect(memberTasks.getByText('Pending approval', {exact: true})).toBeVisible();
      await expect(memberTasks.getByRole('button', {name: 'Approve', exact: true})).toHaveCount(0);
      await page.getByRole('link', {name: 'Tasks', exact: true}).click(); await tasks.getByRole('button', {name: 'Refresh tasks', exact: true}).click();
      await tasks.getByRole('button', {name: title, exact: true}).click();
      await expect(tasks.getByRole('button', {name: 'Approve', exact: true})).toBeEnabled();
      await expect(tasks.getByRole('button', {name: 'Reject', exact: true})).toBeDisabled();
      await expect(tasks.getByRole('button', {name: 'Reopen task', exact: true})).toBeDisabled();
      await tasks.getByLabel('Reason', {exact: true}).fill(' \t\n ');
      await expect(tasks.getByRole('button', {name: 'Reject', exact: true})).toBeDisabled();
      await tasks.getByRole('button', {name: 'Approve', exact: true}).click();
      await expect(tasks.getByText('Approved', {exact: true})).toBeVisible();
      await memberTasks.getByRole('button', {name: 'Refresh tasks', exact: true}).click(); await expect(memberTasks.getByText('Approved', {exact: true})).toBeVisible();
      const items = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json(), id = items.items[0].occurrence_id;
      const approved = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences/' + id)).json();
      expect(approved.cycle.performers[0].role).toBe('restricted'); expect(approved.cycle.verified_by.role).toBe('administrator');
      await expect(tasks.getByRole('button', {name: 'Reopen task', exact: true})).toBeDisabled();
      await tasks.getByLabel('Reason', {exact: true}).fill('Repeat after review');
      await expect(tasks.getByRole('button', {name: 'Reopen task', exact: true})).toBeEnabled();
      // Retain real upstream bytes before delivery; avoid depending on Chromium's
      // response-body cache for the original-result assertion.
      const reopeningResults: {result: {cycle: {closed_at: number | null; performers: unknown}}}[] = [];
      let reopeningWrites = 0;
      await page.route(base(mode) + '/api/v1/tasks/occurrences/' + id + '/reopen', async route => {
        expect(route.request().method()).toBe('POST'); reopeningWrites++;
        const upstream = await route.fetch({maxRetries: 0, maxRedirects: 0}); expect(upstream.status()).toBe(200);
        const body = await upstream.body(); reopeningResults.push(JSON.parse(body.toString('utf8')));
        await route.fulfill({response: upstream, body});
      });
      const currentLocation = page.url();
      await tasks.getByRole('button', {name: 'Reopen task', exact: true}).click();
      await expect(tasks.getByRole('button', {name: 'Mark done now', exact: true})).toBeVisible();
      expect(page.url()).toBe(currentLocation); expect(reopeningWrites).toBe(1); expect(reopeningResults).toHaveLength(1);
      const [original] = reopeningResults;
      expect(original.result.cycle.closed_at).not.toBeNull(); expect(original.result.cycle.performers).toEqual(approved.cycle.performers);
      const reopened = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences/' + id)).json();
      expect(reopened.work.state).toBe('assigned'); expect(reopened.work.revision).toBe(5); expect(reopened.cycle).toBeNull();
      expect((await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json()).items).toHaveLength(1);
    } finally {await peer.close();}
  });
  test('Unicode field limits retain invalid input and accept exact maximum code-point values', async ({page, context}) => {
    const tasks = await open(page, context, mode); let writes = 0;
    page.on('request', request => {if (request.method() === 'POST' && request.url().endsWith('/api/v1/tasks/definitions')) writes++;});
    const titleField = tasks.getByLabel('Title', {exact: true});
    await titleField.fill('   ');
    await tasks.getByRole('button', {name: 'Create task', exact: true}).click();
    await expect(titleField).toBeFocused();
    await expect(titleField).toHaveAttribute('aria-invalid', 'true');
    await expect(tasks.getByText('Enter a title.', {exact: true})).toBeVisible();
    expect(writes).toBe(0);
    await titleField.fill('a'.repeat(161));
    await expect(tasks.getByLabel('Title', {exact: true})).toHaveAttribute('aria-invalid', 'true');
    await expect(tasks.getByRole('button', {name: 'Create task', exact: true})).toBeDisabled();
    await expect(tasks.getByLabel('Title', {exact: true})).toHaveValue('a'.repeat(161)); expect(writes).toBe(0);
    const title = '🧹'.repeat(160), description = '🧼'.repeat(4000);
    await tasks.getByLabel('Title', {exact: true}).fill(title);
    await tasks.getByLabel('Description', {exact: true}).fill('a'.repeat(4001));
    await expect(tasks.getByLabel('Description', {exact: true})).toHaveAttribute('aria-invalid', 'true');
    await expect(tasks.getByRole('button', {name: 'Create task', exact: true})).toBeDisabled(); expect(writes).toBe(0);
    await tasks.getByLabel('Description', {exact: true}).fill(description);
    await tasks.getByRole('button', {name: 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: title, exact: true})).toBeVisible(); expect(writes).toBe(1);
    const list = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json();
    const work = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences/' + list.items[0].occurrence_id)).json();
    expect(work.work.definition_snapshot.content).toMatchObject({title, description});
  });
  test('lost committed response survives reload and recovers by GET without a duplicate creation', async ({page, context}) => {
    const tasks = await open(page, context, mode); let writes = 0, reads = 0;
    page.on('request', request => {if (request.url().includes('/tasks/requests/')) reads++;});
    await page.route(base(mode) + '/api/v1/tasks/definitions', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      writes++; const upstream = await route.fetch({maxRetries: 0, maxRedirects: 0}); expect(upstream.status()).toBe(200);
      await route.abort('connectionreset');
    });
    await tasks.getByLabel('Title', {exact: true}).fill('One original task');
    await tasks.getByRole('button', {name: 'Create task', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: 'Result not confirmed', exact: true})).toBeVisible();
    await page.reload(); await tasks.getByRole('button', {name: 'Check saved request', exact: true}).click();
    await expect(tasks.getByRole('heading', {name: 'Task change saved', exact: true})).toBeVisible();
    expect(writes).toBe(1); expect(reads).toBe(1);
    const actual = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json(); expect(actual.items).toHaveLength(1);
    expect(actual.items[0].title).toBe('One original task');
  });
});

for (const mode of ['native', 'standalone'] as const) {
  for (const locale of ['en', 'es'] as const) {
    test(`protected calendar and fixed batch review use actual stored work in ${mode} ${locale}`, async ({page, context, request}) => {
      expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
      const tasks = await open(page, context, mode);
      const response = await request.post(origin(mode) + '/__fixture__/calendar-review');
      expect(response.status()).toBe(200);
      const {title, completed, started, future, first, new_date: newDate} = await response.json();
      const t = (english: string, spanish: string) => locale === 'en' ? english : spanish;
      if (locale === 'es') await page.getByLabel('Language', {exact: true}).selectOption('es');
      await page.setViewportSize({width: 320, height: 720});
      const tab = page.getByRole('link', {name: t('Calendar', 'Calendario'), exact: true});
      await tab.focus();
      await page.keyboard.press('Enter');
      const calendar = page.locator('domus-calendar');
      await expect(calendar.locator('.calendar-grid')).toBeVisible();
      await expect(page.locator('domus-app #calendar')).toBeFocused();
      const view = calendar.getByRole('combobox', {name: t('Calendar view', 'Vista del calendario')});
      await view.focus();
      await view.press('a');
      await expect(view).toHaveValue('agenda');
      await calendar.getByLabel(t('Reference date', 'Fecha de referencia')).fill(first);
      const show = calendar.getByRole('button', {name: t('Show calendar', 'Mostrar calendario')});
      await show.focus();
      await page.keyboard.press('Enter');
      await expect(calendar.locator('.calendar-grid')).toHaveCount(0);
      const rows = calendar.locator('.calendar-entries li').filter({hasText: title});
      for (const kind of [t('Planned', 'Previsto'), t('Due', 'Vencimiento'), t('Performed', 'Realizado'), t('Approval', 'Aprobación')])
        await expect(rows.filter({hasText: kind}).first().locator('time')).toBeVisible();
      await expect(calendar.getByRole('status').filter({hasText: t('Recurrence processing is pending.', 'Hay recurrencias pendientes de procesar.')})).toBeVisible();
      await expect(calendar.locator('img,script')).toHaveCount(0);

      await page.getByRole('link', {name: t('Tasks', 'Tareas'), exact: true}).click();
      await tasks.getByRole('button', {name: t('Refresh tasks', 'Actualizar tareas')}).click();
      const endpoint = base(mode) + '/api/v1/tasks/occurrences';
      const before = (await (await page.request.get(endpoint)).json()).items;
      const candidates = before.filter((item: {title: string}) => item.title === title);
      const candidateIndex = candidates.findIndex((item: {occurrence_id: string}) => item.occurrence_id === future);
      expect(candidateIndex).toBeGreaterThanOrEqual(0);
      await tasks.getByRole('button', {name: title, exact: true}).nth(candidateIndex).click();
      const review = page.locator('domus-recurrence-review');
      await review.getByRole('button', {name: t('Review scheduling', 'Revisar programación'), exact: true}).click();
      await review.getByRole('combobox').first().selectOption('fixed-replacement');
      await review.getByLabel(t('Local date', 'Fecha local')).fill(newDate);
      await review.locator('input[name=time]').fill('07:00');
      await review.locator('input[name=pattern]').fill('FREQ=DAILY;COUNT=1');
      const reason = '<img src=x onerror=alert(1)> reviewed reason';
      await review.locator('textarea[name=reason]').fill(reason);
      await review.getByRole('button', {name: t('Preview schedule change', 'Previsualizar cambio de programación'), exact: true}).click();
      await expect(review.getByText(reason, {exact: true})).toBeVisible();
      await expect(review.locator('img,script')).toHaveCount(0);
      const retained = review.getByRole('list', {name: t('Existing work retained', 'Trabajo existente que se conserva')});
      await expect(retained.getByRole('listitem')).not.toHaveCount(0);
      let applies = 0;
      let originalKey = '';
      await page.route(base(mode) + '/api/v1/tasks/recurrence/reviews/fixed-replacement/apply', async route => {
        applies++;
        originalKey = route.request().headers()['idempotency-key'];
        const committed = await route.fetch({maxRetries: 0, maxRedirects: 0});
        expect(committed.status()).toBe(200);
        await route.abort('connectionreset');
      });
      await review.getByRole('button', {name: t('Apply reviewed change', 'Aplicar cambio revisado'), exact: true}).click();
      await expect(review.getByRole('alert')).toContainText(t('The result is unconfirmed', 'El resultado no está confirmado'));
      await page.reload();
      await expect(review.getByRole('button', {name: 'Check original schedule request', exact: true}).last()).toBeVisible();
      if (locale === 'es') await page.getByLabel('Language', {exact: true}).selectOption('es');
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      const recovered = page.waitForResponse(item => item.request().method() === 'GET' && item.url().endsWith('/' + originalKey));
      await review.getByRole('button', {name: t('Check original schedule request', 'Consultar solicitud de programación original'), exact: true}).last().click();
      expect((await recovered).ok()).toBe(true);
      await expect(review.getByRole('heading', {name: t('Schedule change saved', 'Cambio de programación guardado'), exact: true})).toBeVisible();
      expect(applies).toBe(1);
      const after = (await (await page.request.get(endpoint)).json()).items;
      expect(after).toEqual(expect.arrayContaining([
        expect.objectContaining({occurrence_id: completed, state: 'completed'}),
        expect.objectContaining({occurrence_id: started, state: 'in_progress'}),
        expect.objectContaining({occurrence_id: future, state: 'cancelled'}),
      ]));
    });
  }
}

for (const mode of ['native', 'standalone'] as const) {
  for (const locale of ['en', 'es'] as const) {
    test(`assignment review, recovery and restart in ${mode} ${locale}`, async ({browser, request}, info) => {
      test.setTimeout(75_000);
      expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
      const owner = await browser.newContext({viewport: {width: locale === 'es' ? 390 : 1280, height: 844}, hasTouch: locale === 'es'});
      const peer = await browser.newContext();
      const page = await owner.newPage(), participant = await peer.newPage();
      const subject = mode === 'native' ? 'c' : 'b';
      const t = (english: string, spanish: string) => locale === 'en' ? english : spanish;
      const activate = async (target: Locator) => {
        if (locale === 'es') await target.tap();
        else {await target.focus(); await target.press('Enter');}
      };
      const signIn = async () => {
        if (mode === 'standalone') {
          await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
          await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
        }
        await expect(page.getByRole('link', {name: 'Tasks', exact: true})).toBeVisible();
        await page.getByRole('link', {name: 'Tasks', exact: true}).click();
        await expect(page.locator('domus-tasks').getByRole('heading', {name: /^(Household tasks|Tareas del hogar)$/u})).toBeVisible();
        await page.getByRole('combobox', {name: /^(Language|Idioma)$/u}).selectOption(locale);
      };
      try {
        const tasks = await open(page, owner, mode);
        await page.getByRole('link', {name: 'Household', exact: true}).click();
        const administration = page.locator('domus-administration');
        await administration.getByRole('button', {name: 'Edit access rules', exact: true}).click();
        await administration.getByLabel('HA administrator mapping', {exact: true}).selectOption('selected_ha_user');
        await administration.getByLabel('Target Home Assistant account', {exact: true}).selectOption('a'.repeat(32));
        await saveAdministration(administration);
        if (mode === 'native') await peer.addCookies([{name: 'ingress_session', value: 'e'.repeat(128), domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
        else await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: subject.repeat(32)}});
        await participant.goto(base(mode) + '/');
        if (mode === 'standalone') {
          await participant.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
          await participant.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
        }
        await participant.getByRole('button', {name: 'Request membership', exact: true}).click();
        await expect(participant.getByRole('heading', {name: 'Membership pending', exact: true})).toBeVisible();
        if (mode === 'standalone') await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'a'.repeat(32)}});
        await administration.getByRole('button', {name: 'Refresh administration', exact: true}).click();
        await administration.getByRole('button', {name: 'Manage participant: Fictional account ' + subject, exact: true}).click();
        await administration.getByLabel('Membership status', {exact: true}).selectOption('active');
        await administration.getByRole('button', {name: 'Review changes', exact: true}).click();
        await administration.getByRole('checkbox', {name: 'Approve household access', exact: true}).check();
        await administration.getByRole('button', {name: 'Review changes', exact: true}).click();
        await administration.getByRole('button', {name: 'Save changes', exact: true}).click();
        await expect(administration.getByRole('heading', {name: 'Original request processed', exact: true})).toBeVisible();
        await administration.getByRole('button', {name: 'Close editor', exact: true}).click();
        await participant.getByRole('button', {name: 'Refresh status', exact: true}).click();
        await participant.getByRole('link', {name: 'Tasks', exact: true}).click();
        const ownerAccess = await (await page.request.get(base(mode) + '/api/v1/tasks/access')).json();
        const peerAccess = await (await participant.request.get(base(mode) + '/api/v1/tasks/access')).json();
        await page.getByRole('combobox', {name: 'Language', exact: true}).selectOption(locale);
        await page.getByRole('link', {name: t('Tasks', 'Tareas'), exact: true}).click();
        const title = 'Assign <kitchen> & help';
        await tasks.getByLabel(t('Title', 'Título'), {exact: true}).fill(title);
        await activate(tasks.getByRole('button', {name: t('Create task', 'Crear tarea'), exact: true}));
        await expect(tasks.getByRole('heading', {name: title, exact: true})).toBeVisible();
        const list = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json();
        const id = list.items.find((item: {title: string}) => item.title === title).occurrence_id;
        const endpoint = base(mode) + '/api/v1/tasks/occurrences/' + id;
        const writes: {key: string; body: string; context: string}[] = [];
        page.on('request', item => {
          if (item.method() === 'PUT' && item.url() === endpoint + '/assignment')
            writes.push({key: item.headers()['idempotency-key'], body: item.postData()!, context: item.headers()['x-domus-context']});
        });
        const edit = tasks.getByRole('button', {name: t('Change assignment', 'Cambiar asignación'), exact: true});
        const save = tasks.getByRole('button', {name: t('Save assignment', 'Guardar asignación'), exact: true});
        const ownChoice = tasks.getByRole('checkbox', {name: 'Fictional account a', exact: true});
        const peerChoice = tasks.getByRole('checkbox', {name: 'Fictional account ' + subject, exact: true});
        const toggle = async (target: Locator) => {
          if (locale === 'es') await target.tap();
          else {await target.focus(); await target.press('Space');}
        };
        await activate(edit);
        await expect(save).toBeDisabled();
        await expect(tasks.getByText(t('Choose a different assignment to save a change.',
          'Elige una asignación diferente para guardar un cambio.'), {exact: true})).toBeVisible();
        expect(writes).toEqual([]);
        await toggle(ownChoice); await toggle(peerChoice);
        await activate(tasks.getByRole('button', {name: t('Cancel', 'Cancelar'), exact: true}));
        expect(writes).toEqual([]);
        await activate(edit); await expect(ownChoice).not.toBeChecked();
        await toggle(ownChoice); await toggle(peerChoice); await activate(save);
        await expect(tasks.getByRole('heading', {name: t('Assignment saved', 'Asignación guardada'), exact: true})).toBeVisible();
        expect(JSON.parse(writes[0].body)).toEqual({expected_revision: 1, assignee_ids: [ownerAccess.member_id, peerAccess.member_id]});
        expect((await (await page.request.get(endpoint)).json()).work.assignee_ids.sort()).toEqual([ownerAccess.member_id, peerAccess.member_id].sort());
        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'snapshot'}})).ok()).toBe(true);

        await activate(edit); await expect(save).toBeDisabled();
        await toggle(ownChoice); await expect(save).toBeEnabled();
        await toggle(ownChoice); await expect(save).toBeDisabled();
        expect(writes).toHaveLength(1);
        await toggle(ownChoice);
        const concurrent = await owner.newPage();
        await concurrent.goto(base(mode) + '/#tasks');
        const competing = concurrent.locator('domus-tasks');
        await competing.getByRole('button', {name: title, exact: true}).click();
        await competing.getByRole('button', {name: 'Change assignment', exact: true}).click();
        await competing.getByRole('checkbox', {name: 'Fictional account ' + subject, exact: true}).uncheck();
        await competing.getByRole('button', {name: 'Save assignment', exact: true}).click();
        await expect(competing.getByRole('heading', {name: 'Assignment saved', exact: true})).toBeVisible();
        await concurrent.close();
        await activate(save);
        const review = tasks.getByRole('button', {name: t('Review current assignment', 'Revisar asignación actual'), exact: true});
        await expect(review).toBeVisible(); await expect(save).toBeDisabled();
        await expect(ownChoice).not.toBeChecked(); await expect(peerChoice).toBeChecked();
        expect(writes).toHaveLength(1);
        await activate(review); await activate(save);
        await expect(edit).toBeVisible(); expect(JSON.parse(writes[1].body).expected_revision).toBe(3);

        await activate(edit); await activate(tasks.getByRole('button', {name: t('Clear selection', 'Borrar selección'), exact: true}));
        await page.route(endpoint + '/assignment', async route => {
          const committed = await route.fetch({maxRetries: 0, maxRedirects: 0}); expect(committed.status()).toBe(200);
          await route.abort('connectionreset');
        });
        await activate(save);
        await expect(tasks.getByRole('heading', {name: t('Result not confirmed', 'Resultado sin confirmar'), exact: true})).toBeVisible();
        await expect(save).toBeDisabled(); expect(writes).toHaveLength(3);
        const released = writes[2]; expect(JSON.parse(released.body)).toEqual({expected_revision: 4, assignee_ids: []});
        await page.unroute(endpoint + '/assignment'); await page.reload();
        await expect(tasks.getByRole('heading', {name: 'Household tasks', exact: true})).toBeVisible();
        await page.getByRole('combobox', {name: 'Language', exact: true}).selectOption(locale);
        await activate(tasks.getByRole('button', {name: t('Check saved request', 'Comprobar solicitud guardada'), exact: true}).first());
        await expect(tasks.getByRole('heading', {name: t('Assignment saved', 'Asignación guardada'), exact: true})).toBeVisible();
        expect(writes).toHaveLength(3);
        const original = await (await page.request.get(base(mode) + '/api/v1/tasks/requests/task.assign/' + released.key)).json();
        expect(original).toMatchObject({state: 'committed', result: {assignee_ids: [], revision: 5, state: 'available'}});
        await expect(tasks.locator('.assignment')).toContainText(t('Unassigned', 'Sin asignar'));
        await activate(edit); await toggle(peerChoice); await activate(save); await expect(edit).toBeVisible();
        const retained = writes[3];
        const operation = await (await page.request.get(base(mode) + '/api/v1/tasks/requests/task.assign/' + retained.key)).json();
        expect(operation.result).toMatchObject({assignee_ids: [peerAccess.member_id], revision: 6});
        await page.screenshot({path: info.outputPath('assignment-' + mode + '-' + locale + '.png'), fullPage: true});
        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'restart'}})).ok()).toBe(true);
        await page.reload(); await signIn(); await activate(tasks.getByRole('button', {name: title, exact: true}));
        expect((await (await page.request.get(endpoint)).json()).work).toMatchObject({revision: 6, assignee_ids: [peerAccess.member_id]});
        expect(await (await page.request.get(base(mode) + '/api/v1/tasks/requests/task.assign/' + retained.key)).json())
          .toMatchObject({operation_id: operation.operation_id, result: operation.result});
        await activate(tasks.getByRole('button', {name: t('Mark done now', 'Marcar como hecha ahora'), exact: true}));
        await expect(tasks.getByText(t('No approval required', 'No necesita aprobación'), {exact: true})).toBeVisible();
        const completed = await (await page.request.get(endpoint)).json();
        expect(completed.cycle.performers.map((item: {member_id: string}) => item.member_id)).toEqual([ownerAccess.member_id]);
        expect(completed.work.assignee_ids).toEqual([peerAccess.member_id]);

        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'restore'}})).ok()).toBe(true);
        await page.reload(); await signIn();
        const before = await (await request.get(origin(mode) + '/__fixture__/stats')).json();
        const csrf = await (await page.request.get(base(mode) + '/api/v1/auth/csrf')).json();
        const replay = await page.request.put(endpoint + '/assignment', {data: retained.body, headers: {'Content-Type': 'application/json', Origin: origin(mode),
          'X-CSRF-Token': csrf.csrf_token, 'Idempotency-Key': retained.key, 'X-Domus-Context': retained.context}});
        expect(replay.status()).toBe(200);
        expect(await replay.json()).toMatchObject({state: 'historical', operation_id: operation.operation_id, result: operation.result});
        expect((await (await page.request.get(endpoint)).json()).work).toMatchObject({revision: 2, state: 'assigned'});
        expect((await (await page.request.get(endpoint)).json()).work.assignee_ids.sort()).toEqual([ownerAccess.member_id, peerAccess.member_id].sort());
        expect((await (await request.get(origin(mode) + '/__fixture__/stats')).json()).counts).toEqual(before.counts);
        await info.attach('assignment-operation-evidence', {body: JSON.stringify({mode, locale, writes, operationId: operation.operation_id,
          originalRelease: original.operation_id, restartRevision: 6, restoredRevision: 2, performerId: ownerAccess.member_id}), contentType: 'application/json'});
      } finally {await peer.close(); await owner.close();}
    });
  }
}

for (const mode of ['native', 'standalone'] as const) {
  for (const locale of ['en', 'es'] as const) {
    test(`progress reason, conflict, recovery and restart in ${mode} ${locale}`, async ({browser, request}, info) => {
      test.setTimeout(75_000);
      expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
      const context = await browser.newContext({viewport: {width: locale === 'es' ? 390 : 1280, height: 844}, hasTouch: locale === 'es'});
      const page = await context.newPage();
      const t = (english: string, spanish: string) => locale === 'en' ? english : spanish;
      const contrast = (element: Locator, backgroundProperty: string | null = null) => element.evaluate((node, property) => {
        const style = getComputedStyle(node);
        const luminance = (color: string) => {
          const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
          const context = canvas.getContext('2d')!; context.fillStyle = color; context.fillRect(0, 0, 1, 1);
          const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
            const channel = value / 255; return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        };
        const foreground = luminance(style.color);
        const background = luminance(property === null ? style.backgroundColor : style.getPropertyValue(property));
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      }, backgroundProperty);
      const activate = async (target: Locator) => {
        if (locale === 'es') await target.tap();
        else {await target.focus(); await target.press('Enter');}
      };
      const signIn = async () => {
        if (mode === 'standalone') {
          await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
          await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
        }
        await page.getByRole('link', {name: /^(Tasks|Tareas)$/u, exact: true}).click();
        await expect(page.locator('domus-tasks').getByRole('heading', {name: /^(Household tasks|Tareas del hogar)$/u})).toBeVisible();
        await page.getByRole('combobox', {name: /^(Language|Idioma)$/u}).selectOption(locale);
        await expect(page.getByRole('link', {name: t('Tasks', 'Tareas'), exact: true})).toBeVisible();
      };
      try {
        const tasks = await open(page, context, mode);
        await page.getByRole('combobox', {name: 'Language', exact: true}).selectOption(locale);
        const title = 'Progress <kitchen> 🧰';
        await tasks.getByLabel(t('Title', 'Título'), {exact: true}).fill(title);
        // Await this transaction within the existing HTTP bound before checking its projection.
        const creation = page.waitForResponse(response => response.request().method() === 'POST'
          && response.url() === base(mode) + '/api/v1/tasks/definitions', {timeout: 15_000});
        await activate(tasks.getByRole('button', {name: t('Create task', 'Crear tarea'), exact: true}));
        expect((await creation).status()).toBe(200);
        await expect(tasks.getByRole('heading', {name: title, exact: true})).toBeVisible();
        const list = await (await page.request.get(base(mode) + '/api/v1/tasks/occurrences')).json();
        const id = list.items.find((item: {title: string}) => item.title === title).occurrence_id;
        const endpoint = base(mode) + '/api/v1/tasks/occurrences/' + id;
        const writes: {key: string; body: string; context: string}[] = [];
        page.on('request', item => {
          if (item.method() === 'POST' && item.url() === endpoint + '/transition')
            writes.push({key: item.headers()['idempotency-key'], body: item.postData()!, context: item.headers()['x-domus-context']});
        });
        const block = tasks.getByRole('button', {name: t('Block task', 'Bloquear tarea'), exact: true});
        const unblock = tasks.getByRole('button', {name: t('Unblock task', 'Desbloquear tarea'), exact: true});
        const save = tasks.getByRole('button', {name: t('Save progress', 'Guardar progreso'), exact: true});
        const reason = tasks.getByRole('textbox', {name: t('Reason for blocking', 'Motivo del bloqueo'), exact: true});
        const saved = tasks.getByText(t('Task progress saved', 'Progreso de la tarea guardado'), {exact: true});
        const cancel = tasks.getByRole('button', {name: t('Cancel', 'Cancelar'), exact: true});
        const edit = tasks.getByRole('button', {name: t('Change assignment', 'Cambiar asignación'), exact: true});
        const assign = tasks.getByRole('button', {name: t('Save assignment', 'Guardar asignación'), exact: true});
        const current = async () => (await (await page.request.get(endpoint)).json()).work;
        const explanation = 'Waiting for <parts> & help\n🧰';
        await activate(block); await expect(reason).toBeFocused(); await expect(save).toBeDisabled();
        await reason.fill(' \n\t'); await expect(save).toBeDisabled();
        await reason.fill('A'.repeat(1001)); await expect(save).toBeDisabled();
        await reason.fill(explanation);
        for (const colorScheme of ['light', 'dark'] as const) {
          await page.emulateMedia({colorScheme});
          await expect.poll(() => contrast(tasks.getByRole('article', {name: t('Block task', 'Bloquear tarea'), exact: true}))).toBeGreaterThanOrEqual(4.5);
          await expect.poll(() => contrast(save, '--vyp-ha-primary')).toBeGreaterThanOrEqual(4.5);
          await page.screenshot({path: info.outputPath('progress-editor-' + mode + '-' + locale + '-' + colorScheme + '.png'), fullPage: true});
        }
        await activate(cancel); await expect(block).toBeFocused();
        for (const colorScheme of ['light', 'dark'] as const) {
          await page.emulateMedia({colorScheme});
          await expect.poll(() => contrast(tasks.locator('domus-allocation-settings').getByRole('article'))).toBeGreaterThanOrEqual(4.5);
          await expect.poll(() => contrast(tasks.locator('domus-allocation-settings').getByRole('button',
            {name: t('Save policy', 'Guardar política'), exact: true}), '--vyp-ha-primary')).toBeGreaterThanOrEqual(4.5);
        }
        expect(writes).toEqual([]);
        await activate(block); await reason.fill(explanation); await activate(save); await expect(saved).toBeVisible();
        expect(await current()).toMatchObject({revision: 2, state: 'blocked', state_reason: explanation, assignee_ids: []});
        await expect(tasks.locator('#task-blocked-reason')).toHaveText(explanation);
        await activate(unblock); await activate(save); await expect(block).toBeVisible();
        expect(await current()).toMatchObject({revision: 3, state: 'available', state_reason: '', assignee_ids: []});
        await activate(edit);
        const own = tasks.getByRole('checkbox', {name: 'Fictional account a', exact: true});
        if (locale === 'es') await own.tap(); else {await own.focus(); await own.press('Space');}
        await activate(assign); await expect(edit).toBeVisible();
        const assignees = (await current()).assignee_ids;
        await activate(tasks.getByRole('button', {name: t('Start task', 'Iniciar tarea'), exact: true}));
        await activate(save); await expect(block).toBeVisible();
        expect(await current()).toMatchObject({revision: 5, state: 'in_progress', assignee_ids: assignees});

        await activate(block); await reason.fill(explanation);
        const concurrent = await context.newPage(); await concurrent.goto(base(mode) + '/#tasks');
        const competing = concurrent.locator('domus-tasks');
        await competing.getByRole('button', {name: title, exact: true}).click();
        await competing.getByRole('button', {name: 'Block task', exact: true}).click();
        await competing.getByRole('textbox', {name: 'Reason for blocking', exact: true}).fill('Another member blocked it');
        await competing.getByRole('button', {name: 'Save progress', exact: true}).click();
        await expect(competing.getByText('Task progress saved', {exact: true})).toBeVisible();
        await concurrent.close();
        const beforeConflict = writes.length;
        await activate(save); await expect(save).toBeDisabled(); await expect(reason).toHaveValue(explanation);
        await expect(tasks.getByText(t('Action unavailable', 'Acción no disponible'), {exact: true})).toBeVisible();
        await expect(tasks.getByRole('listitem').filter({hasText: title})).toContainText(t('Blocked', 'Bloqueada'));
        expect(writes).toHaveLength(beforeConflict);
        await activate(tasks.getByRole('button', {name: t('Refresh current task', 'Actualizar tarea actual'), exact: true}));
        await expect(reason).toHaveValue(explanation); await activate(cancel);
        await expect(tasks.locator('#task-blocked-reason')).toHaveText('Another member blocked it');
        await activate(unblock); await activate(save); await expect(block).toBeVisible();
        expect(await current()).toMatchObject({revision: 7, state: 'assigned', assignee_ids: assignees});
        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'snapshot'}})).ok()).toBe(true);

        await activate(block); await reason.fill(explanation);
        const second = await context.newPage(); await second.goto(base(mode) + '/#tasks');
        const other = second.locator('domus-tasks');
        await other.getByRole('button', {name: title, exact: true}).click();
        await other.getByRole('button', {name: 'Change assignment', exact: true}).click();
        await other.getByRole('button', {name: 'Clear selection', exact: true}).click();
        await other.getByRole('button', {name: 'Save assignment', exact: true}).click();
        await expect(other.getByRole('heading', {name: 'Assignment saved', exact: true})).toBeVisible();
        await second.close();
        const beforeReview = writes.length;
        await activate(save);
        const review = tasks.getByRole('button', {name: t('Review current task', 'Revisar tarea actual'), exact: true});
        await expect(review).toBeFocused(); await expect(save).toBeDisabled(); await expect(reason).toHaveValue(explanation);
        await expect(tasks.getByRole('listitem').filter({hasText: title})).toContainText(t('Available', 'Disponible'));
        expect(writes).toHaveLength(beforeReview);
        await activate(review); await expect(save).toBeFocused(); expect(writes).toHaveLength(beforeReview);
        await page.route(endpoint + '/transition', async route => {
          const committed = await route.fetch({maxRetries: 0, maxRedirects: 0}); expect(committed.status()).toBe(200);
          await route.abort('connectionreset');
        });
        await activate(save);
        await expect(tasks.getByRole('heading', {name: t('Result not confirmed', 'Resultado sin confirmar'), exact: true})).toBeVisible();
        await expect(reason).toHaveValue(explanation); await expect(save).toBeDisabled();
        expect(writes).toHaveLength(beforeReview + 1);
        const retained = writes.at(-1)!;
        expect(JSON.parse(retained.body)).toEqual({expected_revision: 8, target: 'blocked', reason: explanation});
        await page.unroute(endpoint + '/transition'); await page.reload();
        await expect(tasks.getByRole('heading', {name: 'Household tasks', exact: true})).toBeVisible();
        await page.getByRole('combobox', {name: 'Language', exact: true}).selectOption(locale);
        await activate(tasks.getByRole('button', {name: t('Check saved request', 'Comprobar solicitud guardada'), exact: true}).first());
        await expect(saved).toBeVisible(); await expect(tasks.locator('#task-blocked-reason')).toHaveText(explanation);
        const originalUrl = base(mode) + '/api/v1/tasks/requests/task.transition/' + retained.key;
        const original = await (await page.request.get(originalUrl)).json();
        expect(original).toMatchObject({state: 'committed', result: {revision: 9, state: 'blocked', state_reason: explanation, assignee_ids: []}});
        const before = await (await request.get(origin(mode) + '/__fixture__/stats')).json();
        const csrf = await (await page.request.get(base(mode) + '/api/v1/auth/csrf')).json();
        const headers = {'Content-Type': 'application/json', Origin: origin(mode), 'X-CSRF-Token': csrf.csrf_token,
          'Idempotency-Key': retained.key, 'X-Domus-Context': retained.context};
        const replay = await page.request.post(endpoint + '/transition', {data: retained.body, headers});
        expect(replay.status()).toBe(200); expect((await replay.json()).operation_id).toBe(original.operation_id);
        const changed = await page.request.post(endpoint + '/transition', {data: {...JSON.parse(retained.body), reason: 'Changed'}, headers});
        expect(changed.status()).toBe(409);
        expect((await (await request.get(origin(mode) + '/__fixture__/stats')).json()).counts).toEqual(before.counts);
        await page.emulateMedia({colorScheme: 'dark'});
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({path: info.outputPath('progress-' + mode + '-' + locale + '-dark.png'), fullPage: true});
        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'restart'}})).ok()).toBe(true);
        await page.reload(); await signIn(); await activate(tasks.getByRole('button', {name: title, exact: true}));
        await expect(tasks.locator('#task-blocked-reason')).toHaveText(explanation);
        expect(await (await page.request.get(originalUrl)).json()).toMatchObject({operation_id: original.operation_id, result: original.result});
        await activate(tasks.getByText(t('Saved requests', 'Solicitudes guardadas'), {exact: true}));
        await activate(tasks.getByRole('button', {name: t('Dismiss saved request', 'Descartar solicitud guardada'), exact: true}).first());
        await activate(unblock); await activate(save); await expect(block).toBeVisible();
        await activate(tasks.getByRole('button', {name: t('Mark done now', 'Marcar como hecha ahora'), exact: true}));
        await expect(tasks.getByText(t('No approval required', 'No necesita aprobación'), {exact: true})).toBeVisible();
        expect((await (await page.request.get(endpoint)).json()).cycle.performers).toHaveLength(1);
        expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'restore'}})).ok()).toBe(true);
        await page.reload(); await signIn();
        const restored = await (await page.request.get(originalUrl)).json();
        expect(restored).toMatchObject({state: 'historical', operation_id: original.operation_id, result: original.result});
        expect(await current()).toMatchObject({revision: 7, state: 'assigned', assignee_ids: assignees});
        const beforeRestoreReplay = await (await request.get(origin(mode) + '/__fixture__/stats')).json();
        const nextCsrf = await (await page.request.get(base(mode) + '/api/v1/auth/csrf')).json();
        const historical = await page.request.post(endpoint + '/transition', {data: retained.body,
          headers: {...headers, 'X-CSRF-Token': nextCsrf.csrf_token}});
        expect(historical.status()).toBe(200); expect(await historical.json()).toMatchObject({state: 'historical', operation_id: original.operation_id});
        expect((await (await request.get(origin(mode) + '/__fixture__/stats')).json()).counts).toEqual(beforeRestoreReplay.counts);
        await info.attach('progress-operation-evidence', {body: JSON.stringify({mode, locale, writes, original: original.operation_id,
          restartRevision: 9, restoredRevision: 7, assignees}), contentType: 'application/json'});
      } finally {await context.close();}
    });
  }
}
