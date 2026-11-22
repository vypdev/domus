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

for(const mode of ['native','standalone'] as const)for(const locale of ['en','es'] as const){
  test.describe(`Unicode text limits ${mode}/${locale}`,()=>{
    test.use({hasTouch:locale==='es',viewport:{width:locale==='es'?390:1120,height:844}});
    test('complete supplementary values survive native entry, validation and protected persistence',async({page,context,request},info)=>{
      test.setTimeout(120_000);
      page.setDefaultTimeout(15_000);
      const origin=`http://127.0.0.1:${mode==='native'?56174:56175}`;
      const base=origin+(mode==='native'?ingress:'')+'/';
      const commands=base+'api/v1/inventory/commands',rewardCommands=base+'api/v1/family/rewards/commands';
      const text=(en:string,es:string)=>locale==='es'?es:en;
      const activate=async(control:ReturnType<typeof page.getByRole>)=>{
        await expect(control).toBeEnabled();
        if(locale==='es')await control.tap();else await control.press('Enter');
      };
      const checkLayout=async()=>expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(locale==='es'?390:1120);
      const errors:string[]=[],external:string[]=[],posts:Record<string,unknown>[]=[];
      page.on('pageerror',error=>errors.push(error.message));
      page.on('request',item=>{if([commands,rewardCommands].includes(item.url())&&item.method()==='POST')posts.push(item.postDataJSON());});
      await context.route('**/*',route=>{
        if(new URL(route.request().url()).origin===origin)return route.continue();
        external.push(route.request().url());return route.abort('internetdisconnected');
      });
      if(process.env.DOMUS_BROWSER_IMAGE){
        const image=await request.get(origin+'/__fixture__/image');expect(image.ok()).toBe(true);
        expect(await image.json()).toEqual({source_commit:process.env.DOMUS_TEST_SOURCE_COMMIT,
          architecture:process.env.DOMUS_TEST_ARCH,image_id:expect.stringMatching(/^sha256:[a-f0-9]{64}$/u),mode});
      }
      expect((await request.post(origin+'/__fixture__/reset')).ok()).toBe(true);
      if(mode==='native')await context.addCookies([{name:'ingress_session',value:'f'.repeat(128),domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
      await page.emulateMedia({colorScheme:locale==='es'?'dark':'light'});
      await page.goto(base+'#household');
      if(mode==='standalone'){
        await page.getByRole('button',{name:'Sign in with Home Assistant',exact:true}).press('Enter');
        await page.getByRole('link',{name:'Continue as fixture user',exact:true}).press('Enter');
      }
      await page.getByRole('textbox',{name:'Household name',exact:true}).fill('Unicode text QA');
      await page.getByRole('textbox',{name:'Timezone',exact:true}).fill('UTC');
      await page.getByRole('button',{name:'Create household',exact:true}).press('Enter');
      const tabs=page.locator('vyp-ha-tabs');await tabs.getByRole('link',{name:'Inventory',exact:true}).press('Enter');
      const stock=page.locator('domus-inventory'),full='😀'.repeat(160);
      // Bind the verified household before choosing the temporary window locale.
      await stock.getByRole('textbox',{name:'Product name',exact:true}).waitFor();
      if(locale==='es')await page.getByLabel('Language',{exact:true}).selectOption(locale);
      await expect(page.locator('html')).toHaveAttribute('lang',locale);
      const name=stock.getByRole('textbox',{name:text('Product name','Nombre del producto'),exact:true});
      // Native typing honors maxlength, unlike a programmatic DOM setter.
      await name.pressSequentially(full+'X');await expect(name).toHaveValue(full+'X');
      const register=stock.getByRole('button',{name:text('Register product','Registrar producto'),exact:true});
      await activate(register);await expect(name).toHaveAttribute('aria-invalid','true');
      await expect(name).toHaveValue(full+'X');expect(posts).toEqual([]);
      await name.fill('');await name.pressSequentially(full);
      const saved=page.waitForResponse(item=>item.url()===commands&&item.request().method()==='POST');
      // Exercise implicit Enter from inside the public Field's shadow input.
      await name.press('Enter');const registration=await saved;expect(registration.status()).toBe(200);
      const householdContext=(await registration.request().allHeaders())['x-domus-context'];expect(householdContext).toBeTruthy();
      await expect(stock.getByRole('article',{name:full,exact:true})).toBeVisible();
      expect(posts[0]).toEqual({action:'inventory.register-product',name:full,base_unit:'piece'});
      await expect(name).toHaveValue('');await expect(name).toHaveAttribute('aria-invalid','false');
      const location=stock.getByRole('textbox',{name:text('Location name','Nombre de la ubicación'),exact:true});
      const locationName='𐐀'.repeat(80);await location.pressSequentially(locationName+'X');
      await activate(stock.getByRole('button',{name:text('Add location','Añadir ubicación'),exact:true}));
      await expect(location).toHaveAttribute('aria-invalid','true');await expect(location).toHaveValue(locationName+'X');expect(posts).toHaveLength(1);
      await location.fill('');await location.pressSequentially(locationName);
      await activate(stock.getByRole('button',{name:text('Add location','Añadir ubicación'),exact:true}));await expect(location).toHaveValue('');
      expect(posts[1]).toEqual({action:'inventory.add-location',name:locationName});
      const product=stock.getByRole('article',{name:full,exact:true});
      await activate(product.getByRole('button',{name:text('Show movement history','Mostrar historial de movimientos'),exact:true}));
      await activate(stock.getByRole('button',{name:text('Adjust stock','Ajustar stock'),exact:true}));
      await stock.getByRole('textbox',{name:text('Signed adjustment quantity','Cantidad del ajuste con signo'),exact:true}).fill('1');
      const reason=stock.getByRole('textbox',{name:text('Reason','Motivo'),exact:true}),fullReason='😀'.repeat(240);
      await reason.pressSequentially(fullReason+'X');await activate(stock.getByRole('button',{name:text('Save adjustment','Guardar ajuste'),exact:true}));
      await expect(reason).toHaveAttribute('aria-invalid','true');await expect(reason).toHaveValue(fullReason+'X');expect(posts).toHaveLength(2);
      await reason.fill('');await reason.pressSequentially(fullReason);
      await activate(stock.getByRole('button',{name:text('Save adjustment','Guardar ajuste'),exact:true}));
      await expect(stock.getByRole('status').filter({hasText:text('Stock adjustment recorded.','Ajuste de stock registrado.')})).toHaveText(text('Stock adjustment recorded. 1 piece','Ajuste de stock registrado. 1 unidad'));
      expect(posts[2]).toMatchObject({action:'inventory.adjust',quantity:'1',reason:fullReason});
      await checkLayout();
      await activate(tabs.getByRole('link',{name:text('Shopping','Compras'),exact:true}));
      const shopping=page.locator('domus-shopping-workspace'),extras=shopping.locator('domus-shopping-list');
      const extraName=extras.getByRole('textbox',{name:text('Extra item name','Nombre del extra'),exact:true});
      await extras.getByRole('textbox',{name:new RegExp('^'+text('Extra quantity','Cantidad del extra'),'u')}).fill('1');
      await extraName.pressSequentially(full+'X');const add=extras.getByRole('button',{name:text('Add manual extra','Añadir extra manual'),exact:true});
      await activate(add);await expect(extraName).toHaveAttribute('aria-invalid','true');await expect(extraName).toHaveValue(full+'X');expect(posts).toHaveLength(3);
      await extraName.fill('');await extraName.pressSequentially(full);await activate(add);await expect(extraName).toHaveValue('');
      expect(posts[3]).toMatchObject({action:'shopping.add-extra',product_id:null,name:full,quantity:'1'});
      await activate(shopping.getByRole('button',{name:text('Show purchases','Mostrar compras'),exact:true}));
      const untracked=shopping.getByRole('textbox',{name:text('Untracked item name','Nombre del artículo sin seguimiento'),exact:true});
      await shopping.getByRole('textbox',{name:text('Quantity purchased','Cantidad comprada'),exact:true}).fill('2');
      await untracked.pressSequentially(full+'X');const buy=shopping.getByRole('button',{name:text('Record purchase','Registrar compra'),exact:true});
      await activate(buy);await expect(untracked).toHaveAttribute('aria-invalid','true');await expect(untracked).toHaveValue(full+'X');expect(posts).toHaveLength(4);
      await untracked.fill('');await untracked.pressSequentially(full);await activate(buy);await expect(untracked).toHaveValue('');
      expect(posts[4]).toEqual({action:'shopping.purchase',product_id:null,name:full,quantity:'2'});
      await checkLayout();
      await activate(tabs.getByRole('link',{name:text('Family','Familia'),exact:true}));
      const rewards=page.locator('domus-rewards');
      const title=rewards.getByRole('textbox',{name:text('Reward name','Nombre de la recompensa'),exact:true});
      await rewards.getByRole('textbox',{name:text('Price in points','Precio en puntos'),exact:true}).fill('1');
      await title.pressSequentially(full+'X');const offer=rewards.getByRole('button',{name:text('Save reward','Guardar recompensa'),exact:true});
      await activate(offer);await expect(title).toHaveAttribute('aria-invalid','true');await expect(title).toHaveValue(full+'X');expect(posts).toHaveLength(5);
      await title.fill('');await title.pressSequentially(full);
      const offered=page.waitForResponse(item=>item.url()===rewardCommands&&item.request().method()==='POST');await activate(offer);
      expect((await offered).status()).toBe(200);await expect(rewards.locator('ol').first().locator('strong')).toHaveText([full]);
      expect(posts[5]).toMatchObject({action:'reward.offer',title:full,cost_minor:100});
      const headers={'X-Domus-Context':householdContext};
      const catalog=await page.request.get(base+'api/v1/inventory',{headers});expect(catalog.status()).toBe(200);
      const inventory=await catalog.json();expect(inventory.products).toHaveLength(1);
      expect(inventory.products[0]).toMatchObject({name:full,recorded:'1',reserved:'0',available:'1'});
      expect(inventory.locations).toContainEqual(expect.objectContaining({name:locationName}));
      const ledger=await page.request.get(base+'api/v1/inventory/products/'+inventory.products[0].product_id+'/movements',{headers});
      expect(ledger.status()).toBe(200);const movements=await ledger.json();
      expect(movements.movements).toHaveLength(1);expect(movements.movements[0]).toMatchObject({reason:fullReason,quantity:'1'});
      const purchased=await page.request.get(base+'api/v1/inventory/purchases',{headers});expect(purchased.status()).toBe(200);
      expect((await purchased.json()).purchases).toEqual([expect.objectContaining({name:full,product_id:null,purchased:'2',received:'0'})]);
      const family=await page.request.get(base+'api/v1/family/rewards',{headers});expect(family.status()).toBe(200);
      expect((await family.json()).catalog).toEqual([expect.objectContaining({offer:expect.objectContaining({title:full})})]);
      await info.attach('unicode-text-commands',{body:JSON.stringify(posts,null,2),contentType:'application/json'});
      await expect(offer).toBeEnabled();
      const colors=await offer.evaluate(element=>{
        // The public surface paints the background inside the transparent hit target.
        const surface=element.querySelector('[part=surface]')!;
        return {foreground:getComputedStyle(surface).color,background:getComputedStyle(surface).backgroundColor};
      });
      const luminance=(value:string)=>{
        const rgb=value.match(/[\d.]+/gu)!.slice(0,3).map(Number).map(channel=>channel/255)
          .map(channel=>channel<=0.04045?channel/12.92:((channel+0.055)/1.055)**2.4);
        return 0.2126*rgb[0]+0.7152*rgb[1]+0.0722*rgb[2];
      };
      const foreground=luminance(colors.foreground),background=luminance(colors.background);
      const contrast=(Math.max(foreground,background)+0.05)/(Math.min(foreground,background)+0.05);
      await title.press('Home');
      expect(contrast).toBeGreaterThanOrEqual(4.5);
      await expect.poll(async()=>{
        const field=await title.boundingBox(),navigation=await tabs.boundingBox();
        return field!.y-Math.max(0,navigation!.y+navigation!.height);
      }).toBeGreaterThanOrEqual(0);
      const fieldBounds=await title.boundingBox(),navigationBounds=await tabs.boundingBox();
      await info.attach('unicode-text-visual-metrics',{body:JSON.stringify({colors,contrast,fieldBounds,navigationBounds}),contentType:'application/json'});
      await page.screenshot({path:info.outputPath('unicode-text-'+locale+'.png')});
      expect(fieldBounds).not.toBeNull();expect(navigationBounds).not.toBeNull();
      expect(fieldBounds!.y).toBeGreaterThanOrEqual(navigationBounds!.y+navigationBounds!.height);
      await checkLayout();
      expect(external).toEqual([]);expect(errors).toEqual([]);
    });
  });
}
