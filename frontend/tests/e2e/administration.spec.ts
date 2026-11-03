import {expect,test} from '@playwright/test';
import type {APIRequestContext,BrowserContext,Locator,Page} from '@playwright/test';

const prefix='/api/hassio_ingress/fixture_domus_supervisor_1234567890';
type Mode='native'|'standalone';
const origin=(mode:Mode)=>`http://127.0.0.1:${mode==='native'?56174:56175}`;
const base=(mode:Mode)=>origin(mode)+(mode==='native'?prefix:'');
const journalKey='domus.administration.journal.v1';
const statistics=async(request:APIRequestContext,mode:Mode)=>(await request.get(origin(mode)+'/__fixture__/stats')).json();
async function signIn(page:Page,mode:Mode) {
  if(mode==='standalone') {
    await page.getByRole('button',{name:'Sign in with Home Assistant',exact:true}).click();
    await page.getByRole('link',{name:'Continue as fixture user',exact:true}).click();
  }
}
async function create(page:Page,context:BrowserContext,mode:Mode) {
  if(mode==='native')await context.addCookies([{name:'ingress_session',value:'f'.repeat(128),domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
  await page.goto(base(mode)+'/');await signIn(page,mode);
  await page.getByLabel('Household name',{exact:true}).fill('Maple House');await page.getByLabel('Timezone',{exact:true}).fill('UTC');
  await page.getByRole('button',{name:'Create household',exact:true}).click();
  const widget=page.locator('domus-administration');await expect(widget.getByRole('heading',{name:'Household administration',exact:true})).toBeVisible();
  await expect(widget.getByRole('button',{name:'Edit preferences',exact:true})).toBeEnabled();return widget;
}
async function save(widget:Locator) {
  await widget.getByRole('button',{name:'Review changes',exact:true}).click();await expect(widget.getByRole('heading',{name:'Confirm this household change',exact:true})).toBeFocused();
  await widget.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(widget.getByRole('heading',{name:'Original request processed',exact:true})).toBeVisible();
  await expect(widget.getByRole('button',{name:'Refresh administration',exact:true})).toBeEnabled();
}
for(const mode of ['native','standalone'] as const)test.describe('administration '+mode,()=>{
  test.beforeEach(async({request})=>{expect((await request.post(origin(mode)+'/__fixture__/reset')).ok()).toBe(true);});
  test('HADW-01: actual independent alias revision, inert text, reload and explicit clear persist through SQLite',async({page,context})=>{
    const widget=await create(page,context,mode);const access=await(await page.request.get(base(mode)+'/api/v1/authorization')).json();
    const path=base(mode)+'/api/v1/administration/members/'+access.member.member_id+'/presentation';
    await widget.getByRole('button',{name:'Edit own alias',exact:true}).click();await widget.getByRole('checkbox',{name:'Use Home Assistant name',exact:true}).uncheck();
    const alias='<img src=x onerror=alert(1)> & Maple';await widget.getByRole('textbox',{name:'Domus alias',exact:true}).fill(alias);await save(widget);
    expect(await(await page.request.get(path)).json()).toEqual({member_id:access.member.member_id,alias,revision:2});await expect(widget.locator('img,script')).toHaveCount(0);
    await page.reload();await expect(widget.getByText(alias,{exact:true}).first()).toBeVisible();
    await widget.getByRole('button',{name:'Edit own alias',exact:true}).click();await widget.getByRole('checkbox',{name:'Use Home Assistant name',exact:true}).check();await save(widget);
    expect(await(await page.request.get(path)).json()).toEqual({member_id:access.member.member_id,alias:null,revision:3});
  });
  test('HADW-02: actual private preference form saves Spanish and the summary choice without delivering a notification',async({page,context,request})=>{
    const widget=await create(page,context,mode);await widget.getByRole('button',{name:'Edit preferences',exact:true}).click();
    await widget.getByLabel('Saved language',{exact:true}).selectOption('es');await widget.getByRole('checkbox',{name:'Routine participation summaries',exact:true}).uncheck();
    await widget.getByRole('button',{name:'Review changes',exact:true}).click();await widget.getByRole('button',{name:'Save changes',exact:true}).click();
    await expect(widget.getByRole('heading',{name:'Petición original procesada',exact:true})).toBeVisible();await expect(page.locator('html')).toHaveAttribute('lang','es');
    expect(await(await page.request.get(base(mode)+'/api/v1/administration/preferences')).json()).toMatchObject({locale:'es',routine_participation_summaries:false,revision:2,notification_delivery:'unavailable'});
    expect((await statistics(request,mode)).counts.receipts).toBe(2);await page.reload();await expect(widget).toHaveAttribute('lang','es');
    await widget.getByRole('button',{name:'Editar preferencias',exact:true}).click();await expect(widget.getByLabel('Idioma guardado',{exact:true})).toHaveValue('es');
    await expect(widget.getByRole('checkbox',{name:'Resúmenes habituales de participación',exact:true})).not.toBeChecked();
  });
  test('HADW-04: actual household form saves the exact name/timezone once and reload reads the persisted revision',async({page,context,request})=>{
    const widget=await create(page,context,mode);await widget.getByRole('button',{name:'Edit household',exact:true}).click();
    await widget.getByRole('textbox',{name:'New household name',exact:true}).fill('Cedar House');await widget.getByRole('textbox',{name:'New timezone',exact:true}).fill('Europe/Madrid');await save(widget);
    expect(await(await page.request.get(base(mode)+'/api/v1/household')).json()).toMatchObject({name:'Cedar House',time_zone:'Europe/Madrid',revision:2});
    expect((await statistics(request,mode)).counts.receipts).toBe(2);await page.reload();await expect(page.getByText('Cedar House',{exact:true})).toBeVisible();
  });
  test('HADW-05: actual mapping/profile form preserves all other profiles and SQLite reauthorizes the selected account',async({page,context})=>{
    const widget=await create(page,context,mode);await widget.getByRole('button',{name:'Edit access rules',exact:true}).click();
    await widget.getByLabel('HA administrator mapping',{exact:true}).selectOption('selected_ha_user');await widget.getByLabel('Target Home Assistant account',{exact:true}).selectOption('a'.repeat(32));
    await widget.getByLabel('Profile to customize',{exact:true}).selectOption('adult');await widget.getByLabel('View tasks',{exact:true}).selectOption('deny');await save(widget);
    expect(await(await page.request.get(base(mode)+'/api/v1/policy')).json()).toMatchObject({revision:2,mapping:{mode:'selected_ha_user',target_ha_user_id:'a'.repeat(32)},
      adjustments:[{role:'adult',permission:'tasks.read',allow:false}]});
    await page.reload();await widget.getByRole('button',{name:'Edit access rules',exact:true}).click();
    await expect(widget.getByLabel('HA administrator mapping',{exact:true})).toHaveValue('selected_ha_user');await expect(widget.getByLabel('View tasks',{exact:true})).toHaveValue('deny');
  });
  test('HADW-04: an actual second HA account requests membership before restricted activation and a later profile change',async({page,context,browser,request})=>{
    const widget=await create(page,context,mode);
    await widget.getByRole('button',{name:'Edit access rules',exact:true}).click();await widget.getByLabel('HA administrator mapping',{exact:true}).selectOption('selected_ha_user');
    await widget.getByLabel('Target Home Assistant account',{exact:true}).selectOption('a'.repeat(32));await save(widget);await widget.getByRole('button',{name:'Close editor',exact:true}).click();
    const peer=await browser.newContext(),other=await peer.newPage();const subject=mode==='native'?'c':'b';
    try {
      if(mode==='native')await peer.addCookies([{name:'ingress_session',value:'e'.repeat(128),domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
      else expect((await request.post(origin(mode)+'/__fixture__/identity',{data:{subject:subject.repeat(32)}})).ok()).toBe(true);
      await other.goto(base(mode)+'/');await signIn(other,mode);await other.getByRole('button',{name:'Request membership',exact:true}).click();
      await expect(other.getByRole('heading',{name:'Membership pending',exact:true})).toBeVisible();
      if(mode==='standalone')await request.post(origin(mode)+'/__fixture__/identity',{data:{subject:'a'.repeat(32)}});
      await widget.getByRole('button',{name:'Refresh administration',exact:true}).click();
      await widget.getByRole('button',{name:'Manage participant: Fictional account '+subject,exact:true}).click();
      await expect(widget.getByLabel('Household profile',{exact:true})).toHaveValue('restricted');await widget.getByLabel('Membership status',{exact:true}).selectOption('active');
      await widget.getByRole('button',{name:'Review changes',exact:true}).click();await expect(widget.getByRole('alert')).toContainText('Confirm household access');
      await widget.getByRole('checkbox',{name:'Approve household access',exact:true}).check();
      await expect(widget.getByRole('region',{name:'Manage participant',exact:true})).toContainText('Participant: Fictional account '+subject);await save(widget);
      const roster=await(await page.request.get(base(mode)+'/api/v1/administration/roster')).json();
      expect(roster.members.find((row:{member:{ha_user_id:string}})=>row.member.ha_user_id===subject.repeat(32)).member).toMatchObject({role:'restricted',status:'active',revision:2});
      await widget.getByRole('button',{name:'Close editor',exact:true}).click();
      await widget.getByRole('button',{name:'Manage participant: Fictional account '+subject,exact:true}).click();
      await expect(widget.getByLabel('Household profile',{exact:true})).toHaveValue('restricted');
      await widget.getByLabel('Household profile',{exact:true}).selectOption('adult');await widget.getByLabel('View tasks',{exact:true}).selectOption('deny');await save(widget);
      const changed=await(await page.request.get(base(mode)+'/api/v1/administration/roster')).json();
      expect(changed.members.find((row:{member:{ha_user_id:string}})=>row.member.ha_user_id===subject.repeat(32)).member)
        .toMatchObject({role:'adult',status:'active',revision:3,exceptions:[{permission:'tasks.read',allow:false}]});

    }finally{await peer.close();}
  });
  test('HADB-02: a lost actual preference PUT reply recovers by original GET without another SQLite mutation',async({page,context,request})=>{
    const widget=await create(page,context,mode),writes:{key:string;body:string|null}[]=[],lookups:string[]=[];
    page.on('request',item=>{if(item.url().includes('/administration/requests/')||item.url().includes('/operations/'))lookups.push(item.url());});
    await page.route(base(mode)+'/api/v1/administration/preferences',async route=>{
      if(route.request().method()!=='PUT')return route.continue();writes.push({key:route.request().headers()['idempotency-key'],body:route.request().postData()});
      const reply=await route.fetch({maxRetries:0,maxRedirects:0});expect(reply.status()).toBe(200);await route.abort('connectionreset');
    });
    await widget.getByRole('button',{name:'Edit preferences',exact:true}).click();await widget.getByLabel('Saved language',{exact:true}).selectOption('en');
    await widget.getByRole('button',{name:'Review changes',exact:true}).click();await widget.getByRole('button',{name:'Save changes',exact:true}).click();
    await expect(widget.getByRole('heading',{name:'Outcome not confirmed',exact:true})).toBeVisible();const before=await statistics(request,mode);
    expect(before.counts.receipts).toBe(2);expect(writes).toHaveLength(1);expect(lookups).toEqual([]);await page.reload();
    await expect(widget.getByRole('button',{name:'Check original request',exact:true})).toBeEnabled();expect(writes).toHaveLength(1);expect(lookups).toEqual([]);
    await widget.getByRole('button',{name:'Check original request',exact:true}).click();await expect(widget.getByRole('heading',{name:'Original request processed',exact:true})).toBeVisible();
    expect(writes).toHaveLength(1);expect(lookups).toEqual([base(mode)+'/api/v1/administration/requests/member.preferences.update/'+writes[0].key]);
    expect(await statistics(request,mode)).toEqual(before);const records=await page.evaluate(key=>JSON.parse(sessionStorage.getItem(key)!).records,journalKey);
    const wirePayload=JSON.parse(writes[0].body!);
    expect(records[0]).toMatchObject({key:writes[0].key,stage:'committed',payload:{...wirePayload,expected_revision:String(wirePayload.expected_revision)}});
  });
  test('HADB-02: stale actual household revision retains the original draft until an explicit reset',async({page,context})=>{
    const widget=await create(page,context,mode);await widget.getByRole('button',{name:'Edit household',exact:true}).click();await widget.getByRole('textbox',{name:'New household name',exact:true}).fill('Unsent draft');
    const csrf=await(await page.request.get(base(mode)+'/api/v1/auth/csrf')).json();expect((await page.request.put(base(mode)+'/api/v1/household',{
      data:{expected_revision:1,name:'Other current name',time_zone:'UTC'},headers:{Origin:origin(mode),'X-CSRF-Token':csrf.csrf_token,'Idempotency-Key':'explicit-concurrent-household'}})).status()).toBe(200);
    await widget.getByRole('button',{name:'Review changes',exact:true}).click();await widget.getByRole('button',{name:'Save changes',exact:true}).click();
    await expect(widget.getByText('The data changed. Your draft keeps its original revision; reset explicitly to adopt current data.',{exact:true})).toBeVisible();
    await expect(widget.getByText('This request was submitted.',{exact:false})).toHaveCount(0);await expect(widget.getByText('New household name',{exact:true})).toBeVisible();
    await expect(widget.getByText('Unsent draft',{exact:true})).toBeVisible();await widget.getByRole('button',{name:'Reset from current data',exact:true}).click();
    await expect(widget.getByRole('textbox',{name:'New household name',exact:true})).toHaveValue('Other current name');
    await widget.getByRole('textbox',{name:'New household name',exact:true}).fill('Explicit new work');await save(widget);
    expect(await(await page.request.get(base(mode)+'/api/v1/household')).json()).toMatchObject({name:'Explicit new work',revision:3});
  });
  test('household-admin-C58: actual compiled keyboard errors and back focus work in both locales with mobile CSP fallback',async({page,context,request},info)=>{
    await page.setViewportSize({width:360,height:800});const violations:string[]=[],writes:string[]=[];
    await page.exposeFunction('administrationCSPViolation',(value:string)=>violations.push(value));
    await page.addInitScript(()=>{
      delete (Document.prototype as {adoptedStyleSheets?:unknown}).adoptedStyleSheets;
      document.addEventListener('securitypolicyviolation',event=>{
        void (window as unknown as {administrationCSPViolation(value:string):Promise<void>}).administrationCSPViolation(event.violatedDirective);
      });
    });
    const widget=await create(page,context,mode),before=await statistics(request,mode);
    page.on('request',item=>{if(item.method()==='PUT')writes.push(item.url());});
    for(const locale of ['en','es'])for(const colorScheme of ['light','dark'] as const) {
      await page.emulateMedia({colorScheme,reducedMotion:'reduce'});await page.locator('domus-app .language select').selectOption(locale);
      const names=locale==='en'?{edit:'Edit own alias',clear:'Use Home Assistant name',alias:'Domus alias',review:'Review changes',back:'Back to editing',cancel:'Cancel',heading:'Confirm this household change'}
        :{edit:'Editar mi alias',clear:'Usar el nombre de Home Assistant',alias:'Alias de Domus',review:'Revisar cambios',back:'Volver a editar',cancel:'Cancelar',heading:'Confirma este cambio del hogar'};
      await widget.getByRole('button',{name:names.edit,exact:true}).click();await expect(widget.getByRole('checkbox',{name:names.clear,exact:true})).toBeFocused();
      await page.keyboard.press('Space');await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Enter');
      await expect(widget.getByRole('checkbox',{name:names.clear,exact:true})).toBeFocused();const id=await widget.getByRole('alert').getAttribute('id');expect(id).not.toBeNull();
      await expect(widget.getByRole('textbox',{name:names.alias,exact:true})).toHaveAttribute('aria-describedby',id!);
      await page.keyboard.press('Tab');await page.keyboard.insertText('Keyboard '+locale);await page.keyboard.press('Tab');await page.keyboard.press('Enter');
      await expect(widget.getByRole('heading',{name:names.heading,exact:true})).toBeFocused();await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Enter');
      await expect(widget.getByRole('checkbox',{name:names.clear,exact:true})).toBeFocused();await expect(widget.getByRole('textbox',{name:names.alias,exact:true})).toHaveValue('Keyboard '+locale);
      const layout=await widget.evaluate(element=>({nonces:[...element.shadowRoot!.querySelectorAll('style')].map(style=>style.nonce),
        background:getComputedStyle(element.shadowRoot!.querySelector('button.primary')!).backgroundColor,width:document.documentElement.scrollWidth}));
      expect(layout.nonces.length).toBeGreaterThan(0);expect(layout.nonces.every(value=>/^[\w-]{32}$/u.test(value))).toBe(true);
      expect(layout.background).not.toBe('rgba(0, 0, 0, 0)');expect(layout.width).toBeLessThanOrEqual(360);expect(violations).toEqual([]);
      await page.screenshot({path:info.outputPath('admin-keyboard-'+locale+'-'+colorScheme+'.png'),fullPage:true});
      await widget.getByRole('button',{name:names.cancel,exact:true}).click();
    }
    expect(writes).toEqual([]);expect(await statistics(request,mode)).toEqual(before);
  });
  test('HADB-02: actual console restoration keeps original history without reviving the removed public alias effect',async({page,context,request})=>{
    const widget=await create(page,context,mode);expect((await request.post(origin(mode)+'/__fixture__/operator',{data:{action:'snapshot'}})).ok()).toBe(true);
    await widget.getByRole('button',{name:'Edit own alias',exact:true}).click();await widget.getByRole('checkbox',{name:'Use Home Assistant name',exact:true}).uncheck();
    await widget.getByRole('textbox',{name:'Domus alias',exact:true}).fill('Rolled away alias');await save(widget);
    expect((await request.post(origin(mode)+'/__fixture__/operator',{data:{action:'restore'}})).ok()).toBe(true);const before=await statistics(request,mode);
    await page.reload();await signIn(page,mode);await expect(widget.getByRole('heading',{name:'Household administration',exact:true})).toBeVisible();
    await expect(widget.getByText('Rolled away alias',{exact:true})).toHaveCount(0);await widget.getByRole('button',{name:'Check original request',exact:true}).click();
    await expect(widget.getByRole('heading',{name:'Processed before restoration',exact:true})).toBeVisible();
    await expect(widget.getByText('This operation was processed before restoration. Its effect is absent from current state.',{exact:true})).toBeVisible();
    await widget.getByRole('button',{name:'Edit own alias',exact:true}).click();await expect(widget.getByRole('checkbox',{name:'Use Home Assistant name',exact:true})).toBeChecked();
    expect((await statistics(request,mode)).counts).toEqual(before.counts);
  });
});
