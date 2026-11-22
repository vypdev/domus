import {expect,test} from '@playwright/test';

const ingress='/api/hassio_ingress/fixture_domus_supervisor_1234567890';
test.use({hasTouch:true,viewport:{width:390,height:844}});

for(const mode of ['native','standalone'] as const)for(const locale of ['en','es'] as const){
  test(`manual shopping annotations preserve literal notes and original recovery in ${mode}/${locale}`,async({page,context,request},info)=>{
    test.setTimeout(90_000);
    const origin=`http://127.0.0.1:${mode==='native'?56174:56175}`;
    const base=origin+(mode==='native'?ingress:'')+'/';
    const commands=base+'api/v1/inventory/commands';
    const external:string[]=[],errors:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    await context.route('**/*',route=>{
      if(new URL(route.request().url()).origin===origin)return route.continue();
      external.push(route.request().url());return route.abort('internetdisconnected');
    });
    if(process.env.DOMUS_BROWSER_IMAGE){
      const response=await request.get(origin+'/__fixture__/image');expect(response.ok()).toBe(true);
      expect(await response.json()).toEqual({source_commit:process.env.DOMUS_TEST_SOURCE_COMMIT,
        architecture:process.env.DOMUS_TEST_ARCH,image_id:expect.stringMatching(/^sha256:[a-f0-9]{64}$/u),mode});
    }
    expect((await request.post(origin+'/__fixture__/reset')).ok()).toBe(true);
    if(mode==='native')await context.addCookies([{name:'ingress_session',value:'f'.repeat(128),domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
    await page.goto(base+'#household');
    if(mode==='standalone'){
      await page.getByRole('button',{name:'Sign in with Home Assistant',exact:true}).press('Enter');
      await page.getByRole('link',{name:'Continue as fixture user',exact:true}).press('Enter');
    }
    await page.getByRole('textbox',{name:'Household name',exact:true}).fill('Shopping annotation QA');
    await page.getByRole('textbox',{name:'Timezone',exact:true}).fill('UTC');
    await page.getByRole('button',{name:'Create household',exact:true}).press('Enter');
    await page.locator('vyp-ha-tabs').getByRole('link',{name:'Inventory',exact:true}).press('Enter');
    const stock=page.locator('domus-inventory');
    await stock.getByRole('textbox',{name:'Product name',exact:true}).fill('QA annotation tea');
    await stock.getByRole('button',{name:'Register product',exact:true}).press('Enter');
    const product=stock.getByRole('article',{name:'QA annotation tea',exact:true});await expect(product).toBeVisible();
    if(locale==='es')await page.getByLabel('Language',{exact:true}).selectOption('es');
    const text=(en:string,es:string)=>locale==='es'?es:en;
    const tabs=page.locator('vyp-ha-tabs');
    await tabs.getByRole('link',{name:text('Shopping','Compras'),exact:true}).tap();
    const workspace=page.locator('domus-shopping-workspace');
    const shared=workspace.locator('domus-shopping-list');
    const item=shared.getByRole('combobox',{name:text('Item to add as an extra','Artículo para añadir como extra'),exact:true});
    const quantity=shared.getByRole('textbox',{name:new RegExp('^'+text('Extra quantity','Cantidad del extra'),'u')});
    const note=shared.getByRole('textbox',{name:text('Note (optional)','Nota (opcional)'),exact:true});
    const priority=shared.getByRole('combobox',{name:text('Priority','Prioridad'),exact:true});
    const save=shared.getByRole('button',{name:text('Add manual extra','Añadir extra manual'),exact:true});
    await item.selectOption({label:'QA annotation tea'});await quantity.fill('2');
    const posts:unknown[]=[];
    page.on('request',item=>{if(item.url()===commands&&item.method()==='POST')posts.push(item.postDataJSON());});
    await note.fill('😀'.repeat(1001));await save.tap();
    await expect(shared.locator('#shopping-extra-error')).toContainText(text('1,000','1.000'));
    await expect(note).toHaveValue('😀'.repeat(1001));await expect(note).toBeFocused();expect(posts).toHaveLength(0);
    for(const control of ['\u0001',...Array.from({length:32},(_,index)=>String.fromCharCode(0x80+index))]){
      await note.fill('Retained');await page.keyboard.insertText('bad'+control);
      await expect(shared.locator('#shopping-extra-error')).toContainText(text('unsupported control characters','caracteres de control no admitidos'));
      await expect(note).toHaveValue('Retained');expect(posts).toHaveLength(0);
    }
    await note.fill('');await note.pressSequentially('First');await note.press('Enter');
    await note.pressSequentially('Second');await page.keyboard.insertText('\t😀 <b>literal</b>');
    const literal='First\nSecond\t😀 <b>literal</b>';
    await expect(note).toHaveValue(literal);expect(posts).toHaveLength(0);
    await priority.focus();await page.keyboard.press('End');await page.keyboard.press('Enter');
    await expect(priority).toContainText(text('Urgent','Urgente'));
    let key='',operation='';let submitted:Record<string,unknown>|null=null;
    await page.route(commands,async route=>{
      submitted=route.request().postDataJSON();key=(await route.request().allHeaders())['idempotency-key'];
      expect(submitted).toMatchObject({action:'shopping.add-extra',quantity:'2',note:literal,priority:'urgent'});
      const upstream=await route.fetch({maxRetries:0,maxRedirects:0});expect(upstream.status()).toBe(200);
      operation=(await upstream.json()).operation_id;await route.abort('connectionclosed');
    });
    await save.tap();
    const recover=workspace.getByRole('button',{name:text('Check original operation','Consultar operación original'),exact:true});
    await expect(recover).toBeEnabled();await expect(note).toHaveValue(literal);
    await expect(priority).toContainText(text('Urgent','Urgente'));expect(posts).toHaveLength(1);
    await page.unroute(commands);
    const pending=await page.evaluate(()=>sessionStorage.getItem('domus.inventory.v1'));
    expect(JSON.parse(pending!).command).toEqual(submitted);
    await page.reload();
    // Bind the verified owner before selecting this window's temporary language.
    await expect(workspace.getByRole('button',{name:/^(Check original operation|Consultar operación original)$/u,exact:true})).toBeEnabled();
    await page.getByLabel(/^(Language|Idioma)$/u,{exact:true}).selectOption(locale);
    await expect(page.locator('html')).toHaveAttribute('lang',locale);
    await expect(recover).toBeEnabled();
    const original=base+'api/v1/inventory/requests/shopping.add-extra/'+key;
    const receipts:unknown[]=[];
    await page.route(original,async route=>{
      const upstream=await route.fetch({maxRetries:0,maxRedirects:0});expect(upstream.status()).toBe(200);
      const body=await upstream.body();receipts.push(JSON.parse(body.toString()));
      await info.attach('shopping-original-receipt',{body,contentType:'application/json'});
      await route.fulfill({response:upstream,body});
    });
    await recover.press('Enter');
    await expect(workspace.getByText(text('Manual extra added.','Extra manual añadido.'),{exact:true})).toBeVisible();
    expect(receipts).toEqual([expect.objectContaining({operation_id:operation})]);expect(posts).toHaveLength(1);
    expect(await page.evaluate(()=>sessionStorage.getItem('domus.inventory.v1'))).toBeNull();
    await page.unroute(original);
    const aggregate=shared.getByRole('listitem').filter({has:page.getByText('QA annotation tea',{exact:true})});
    await expect(aggregate.locator('.manual-annotation')).toHaveCount(0);
    await aggregate.getByRole('button',{name:text('Show shopping sources','Mostrar orígenes de compra'),exact:true}).tap();
    const sources=shared.getByRole('region',{name:text('Show shopping sources','Mostrar orígenes de compra')+' · QA annotation tea',exact:true});
    await expect(sources.locator('.manual-note')).toHaveText(literal);
    await expect(sources.getByText(text('Priority: Urgent','Prioridad: Urgente'),{exact:true})).toBeVisible();
    await expect(sources.locator('b')).toHaveCount(0);
    await tabs.getByRole('link',{name:text('Inventory','Inventario'),exact:true}).tap();
    await expect(product).toBeVisible();await expect(product.locator('dd')).toHaveText(['0','0','0']);
    await tabs.getByRole('link',{name:text('Shopping','Compras'),exact:true}).tap();
    // An independently submitted request retains its own annotation and quantity.
    await item.selectOption({label:'QA annotation tea'});await quantity.fill('1');await note.fill('Separate\nrequest');
    await priority.tap();await shared.getByRole('option',{name:text('Low','Baja'),exact:true}).tap();
    await save.tap();await expect(note).toHaveValue('');await expect(priority).toContainText(text('Normal','Normal'));
    await aggregate.getByRole('button',{name:text('Show shopping sources','Mostrar orígenes de compra'),exact:true}).tap();
    await expect(sources.locator('.manual-note')).toHaveCount(2);
    expect((await sources.locator('.manual-note').allTextContents()).sort()).toEqual([literal,'Separate\nrequest'].sort());
    const firstSource=sources.getByRole('listitem').filter({has:page.getByText(literal,{exact:true})});
    const secondSource=sources.getByRole('listitem').filter({has:page.getByText('Separate\nrequest',{exact:true})});
    await expect(firstSource.locator('dd').first()).toHaveText(text('2 pieces','2 unidades'));
    await expect(secondSource.locator('dd').first()).toHaveText(text('1 piece','1 unidad'));
    // A free-text request accepts exactly 1,000 supplementary codepoints.
    await item.selectOption('');await shared.getByRole('textbox',{name:text('Extra item name','Nombre del extra'),exact:true}).fill('QA maximum note');
    await quantity.fill('1');await note.fill('😀'.repeat(1000));await save.tap();await expect(note).toHaveValue('');
    const free=shared.getByRole('listitem').filter({has:page.getByText('QA maximum note',{exact:true})});
    await expect(free.locator('.manual-note')).toHaveText('😀'.repeat(1000));
    expect(posts).toHaveLength(3);
    expect(posts[2]).toEqual({action:'shopping.add-extra',product_id:null,name:'QA maximum note',quantity:'1',note:'😀'.repeat(1000),priority:'normal'});
    expect(external).toEqual([]);expect(errors).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({path:info.outputPath('shopping-annotations-'+locale+'.png'),fullPage:true});
  });
}
