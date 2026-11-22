import {expect, test} from '@playwright/test';
import type {APIRequestContext, BrowserContext, Locator, Page} from '@playwright/test';

// These are variants of the six cases in the #162 unit of application-experience.md.
// Deployment variants do not create additional native SDD case identities.
const ingress = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';
type Mode = 'native' | 'standalone';
test.use({hasTouch:true});

async function create(page: Page, context: BrowserContext, request: APIRequestContext, mode: Mode) {
  const origin = `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
  const base = origin + (mode === 'native' ? ingress : '') + '/';
  if (process.env.DOMUS_BROWSER_IMAGE) {
    const image = await request.get(origin + '/__fixture__/image');
    expect(image.status()).toBe(200);
    expect(await image.json()).toEqual({source_commit:process.env.DOMUS_TEST_SOURCE_COMMIT,
      architecture:process.env.DOMUS_TEST_ARCH, image_id:expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode});
  }
  expect((await request.post(origin + '/__fixture__/reset')).ok()).toBe(true);
  if (mode === 'native') await context.addCookies([{name:'ingress_session', value:'f'.repeat(128),
    domain:'127.0.0.1', path:'/', httpOnly:true, sameSite:'Strict'}]);
  await page.goto(base + '#household');
  if (mode === 'standalone') {
    await page.getByRole('button', {name:'Sign in with Home Assistant',exact:true}).press('Enter');
    await page.getByRole('link', {name:'Continue as fixture user',exact:true}).press('Enter');
  }
  await page.getByRole('textbox', {name:'Household name',exact:true}).fill('Shopping workspace QA');
  await page.getByRole('textbox', {name:'Timezone',exact:true}).fill('UTC');
  await page.getByRole('button', {name:'Create household',exact:true}).press('Enter');
  const tabs = page.locator('vyp-ha-tabs'), stock = page.locator('domus-app #inventory');
  const shop = page.locator('domus-app #shopping'), commands = base + 'api/v1/inventory/commands';
  const read = page.waitForResponse(response => new URL(response.url()).pathname === new URL(base + 'api/v1/inventory').pathname);
  await tabs.getByRole('link', {name:'Inventory',exact:true}).press('Enter');
  const loaded = await read; expect(loaded.ok()).toBe(true);
  const contextHeader = (await loaded.request().allHeaders())['x-domus-context'];
  expect(contextHeader).toBeTruthy();
  const csrf = await page.request.get(base + 'api/v1/auth/csrf'); expect(csrf.ok()).toBe(true);
  const headers = {Origin:origin, 'X-Domus-Context':contextHeader, 'X-CSRF-Token':(await csrf.json()).csrf_token};
  const write = async (key: string, data: object) => {
    const response = await page.request.post(commands, {headers:{...headers,'Idempotency-Key':key},data});
    expect(response.status(),await response.text()).toBe(200); return await response.json();
  };
  const stats = async () => {
    const response = await request.get(origin + '/__fixture__/stats'); expect(response.ok()).toBe(true);
    return await response.json();
  };
  return {origin,base,tabs,stock,shop,commands,write,stats,headers};
}

async function save(widget: Locator) {
  await widget.getByRole('button', {name:'Review changes',exact:true}).click();
  await widget.getByRole('button', {name:'Save changes',exact:true}).click();
  await expect(widget.getByRole('heading', {name:'Original request processed',exact:true})).toBeVisible();
  await widget.getByRole('button', {name:'Close editor',exact:true}).click();
}

async function expectVisibleItem(row: Locator, tabs: Locator) {
  await expect(row).toBeFocused();
  await expect.poll(async () => {
    const item = await row.boundingBox(), navigation = await tabs.boundingBox();
    return item !== null && navigation !== null && item.y >= navigation.y + navigation.height - 1
      && item.y + item.height <= 844;
  }).toBe(true);
}

for (const mode of ['native','standalone'] as const) {
  test(`inventory1-C01 (#162): distinct localized Shopping, keyboard, touch and overflow in ${mode}`, async ({page,context,request},info) => {
    const {base,tabs,shop,stock,stats} = await create(page,context,request,mode);
    const before = await stats(), mutations:string[] = [];
    page.on('request', item => {if (item.url().startsWith(base + 'api/v1/') && item.method() !== 'GET') mutations.push(item.url());});
    for (const locale of ['en','es'] as const) for (const theme of ['light','dark'] as const) {
      const name = locale === 'en' ? 'Shopping' : 'Compras';
      await page.getByLabel(/^(Language|Idioma)$/u,{exact:true}).selectOption(locale);
      await page.setViewportSize({width:locale === 'en' ? 1120 : 390,height:844});
      await page.emulateMedia({colorScheme:theme});
      const tab = tabs.getByRole('link', {name,exact:true});
      await tab.focus(); await tab.press('Enter');
      await expect(shop).toBeFocused(); await expect(tab).toHaveAttribute('aria-current','page');
      await expect(shop.getByRole('heading', {name,exact:true,level:2})).toBeVisible();
      await expect(shop.getByRole('heading', {name:locale === 'en' ? 'Shared shopping list' : 'Lista compartida de compras',exact:true})).toBeVisible();
      await expect(shop.getByRole('button', {name:locale === 'en' ? 'Add manual extra' : 'Añadir extra manual',exact:true})).toBeEnabled();
      await expect(shop.getByRole('button', {name:locale === 'en' ? 'Show purchases' : 'Mostrar compras',exact:true})).toBeEnabled();
      await expect(shop.getByRole('textbox', {name:locale === 'en' ? 'Product name' : 'Nombre del producto',exact:true})).toHaveCount(0);
      await expect(stock).toBeHidden();
      await expect(tab).toHaveCSS('border-bottom-width','2px');
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(locale === 'en' ? 1120 : 390);
      // Returning from a form must reveal the destination heading below the
      // sticky navigation, including repeated activation of the current tab.
      await shop.getByRole('textbox', {name:locale === 'en' ? 'Note (optional)' : 'Nota (opcional)',exact:true}).focus();
      if (locale === 'es') await tab.tap(); else await tab.press('Enter');
      await expect(shop).toBeFocused();
      await expect.poll(async () => {
        const heading = await shop.getByRole('heading', {name,exact:true,level:2}).boundingBox();
        const navigation = await tabs.boundingBox();
        return heading !== null && navigation !== null && heading.y >= navigation.y + navigation.height - 1
          && heading.y < 844 / 2;
      }).toBe(true);
      await shop.getByRole('link', {name:locale === 'en' ? 'Manage products and stock in Inventory' : 'Gestionar productos y stock en Inventario',exact:true}).press('Enter');
      await expect(stock).toBeFocused(); await expect(stock.locator('domus-shopping')).toHaveCount(0);
      await expect(stock.getByRole('button', {name:locale === 'en' ? 'Register product' : 'Registrar producto',exact:true})).toBeEnabled();
      await tab.press('Enter');
      await page.screenshot({path:info.outputPath(`shopping-${locale}-${theme}.png`),fullPage:true});
    }
    expect(mutations).toEqual([]); expect(await stats()).toEqual(before);
  });

  test(`inventory1-C02 (#162): direct, history, Overview and legacy item entry in ${mode}`, async ({page,context,request},info) => {
    await page.setViewportSize({width:390,height:844});
    const {base,tabs,shop,write,stats} = await create(page,context,request,mode);
    const product = (await write('navigation-product',{action:'inventory.register-product',name:'Navigation tea',base_unit:'piece'})).result;
    await write('navigation-policy',{action:'inventory.configure-replenishment',product_id:product.product_id,minimum:'1',target:'2',expected_revision:'0'});
    const extra = (await write('navigation-extra',{action:'shopping.add-extra',product_id:null,name:'Navigation bags',quantity:'1'})).result;
    const before = await stats(), mutations:string[] = [];
    page.on('request', item => {if(item.url().startsWith(base + 'api/v1/') && item.method() !== 'GET') mutations.push(item.url());});
    const list = shop.locator('domus-shopping-list');
    for (const [kind,id,name] of [['product',product.product_id,'Navigation tea'],['extra',extra.extra_id,'Navigation bags']]) {
      await page.goto(base + '#shopping/' + kind + ':' + id);
      const row = list.getByRole('listitem').getByText(name,{exact:true});
      await expectVisibleItem(row,tabs);
      await page.reload(); await expectVisibleItem(row,tabs);
      await tabs.getByRole('link',{name:'Inventory',exact:true}).press('Enter');
      await page.goBack();
      await expect(page).toHaveURL(base + '#shopping/' + kind + ':' + id);
      await expectVisibleItem(row,tabs).catch(async error => {
        const observation = await page.evaluate(() => {
          const focus:string[] = []; let element = document.activeElement;
          while(element) {focus.push(element.tagName+'#'+element.id+':'+element.textContent?.slice(0,90));element=element.shadowRoot?.activeElement??null;}
          return {url:location.href,focus};
        });
        await info.attach('back-navigation-focus',{body:JSON.stringify(observation),contentType:'application/json'}); throw error;
      });
      await page.goForward(); await expect(page.locator('domus-app #inventory')).toBeFocused();
      await tabs.getByRole('link',{name:'Overview',exact:true}).press('Enter');
      await page.locator('domus-shopping-attention').getByRole('link',{name:new RegExp('^'+name+' ')}).press('Enter');
      await expect(page).toHaveURL(base + '#shopping/' + kind + ':' + id); await expectVisibleItem(row,tabs);
      await page.evaluate(fragment => {location.hash = fragment;},'inventory-shopping/' + kind + ':' + id);
      await expectVisibleItem(row,tabs);
      await expect(tabs.getByRole('link',{name:'Shopping',exact:true})).toHaveAttribute('aria-current','page');
    }
    await page.goto(base + '#shopping');
    await tabs.getByRole('link',{name:'Shopping',exact:true}).press('Enter'); await expect(shop).toBeFocused();
    for (const fragment of ['shopping/product:%ZZ','shopping/extra:','shopping%2Funknown','unrecognized']) {
      await page.evaluate(value => {location.hash = value;},fragment);
      await expect(page).toHaveURL(base + '#' + fragment);
      await expect(tabs.getByRole('link',{name:'Overview',exact:true})).toHaveAttribute('aria-current','page');
    }
    expect(mutations).toEqual([]); expect(await stats()).toEqual(before);
  });

  test(`inventory1-C03 (#162): retained drafts and one interrupted operation across destinations in ${mode}`, async ({page,context,request},info) => {
    const {base,tabs,stock,shop,write,commands,stats} = await create(page,context,request,mode);
    await write('draft-session-item',{action:'shopping.add-extra',product_id:null,name:'Selected bags',quantity:'2'});
    await stock.getByRole('textbox',{name:'Product name',exact:true}).fill('Unsent Stock product');
    await tabs.getByRole('link',{name:'Shopping',exact:true}).press('Enter');
    const list = shop.locator('domus-shopping-list');
    const note = list.getByRole('textbox',{name:'Note (optional)',exact:true});
    const literal = 'First\nSecond\t😀 <em>literal</em>';
    await list.getByRole('textbox',{name:'Extra item name',exact:true}).fill('Unsent extra');
    await list.getByRole('textbox',{name:/^Extra quantity/u}).fill('3'); await note.fill(literal);
    await list.getByRole('combobox',{name:'Priority',exact:true}).focus();
    await page.keyboard.press('End'); await page.keyboard.press('Enter');
    await list.getByRole('listitem').filter({has:page.getByText('Selected bags',{exact:true})})
      .getByRole('button',{name:'Add to purchase session',exact:true}).click();
    const draftSession = list.getByRole('form',{name:'Review purchase session',exact:true});
    await draftSession.getByRole('textbox',{name:'Store (optional)',exact:true}).fill('Unsent shop');
    await tabs.getByRole('link',{name:'Inventory',exact:true}).press('Enter');
    await expect(stock.getByRole('textbox',{name:'Product name',exact:true})).toHaveValue('Unsent Stock product');
    await tabs.getByRole('link',{name:'Shopping',exact:true}).press('Enter');
    await expect(note).toHaveValue(literal);
    await expect(list.getByRole('combobox',{name:'Priority',exact:true})).toContainText('Urgent');
    await expect(draftSession.getByRole('textbox',{name:'Store (optional)',exact:true})).toHaveValue('Unsent shop');
    await shop.getByRole('button',{name:'Show purchases',exact:true}).click();
    await shop.getByRole('textbox',{name:'Untracked item name',exact:true}).fill('One original purchase');
    await shop.getByRole('textbox',{name:'Quantity purchased',exact:true}).fill('1');
    const before = await stats(), posts:unknown[] = []; let key = '', operation = '';
    page.on('request', item => {if(item.url() === commands && item.method() === 'POST') posts.push(item.postDataJSON());});
    await page.route(commands,async route => {
      key = (await route.request().allHeaders())['idempotency-key'];
      const upstream = await route.fetch({maxRetries:0,maxRedirects:0}); expect(upstream.status()).toBe(200);
      operation = (await upstream.json()).operation_id; await route.abort('connectionclosed');
    });
    await shop.getByRole('button',{name:'Record purchase',exact:true}).click();
    const recover = shop.getByRole('button',{name:'Check original operation',exact:true});
    await expect(recover).toBeEnabled(); await page.unroute(commands);
    const pending = await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'));
    expect(JSON.parse(pending!).key).toBe(key);
    await tabs.getByRole('link',{name:'Inventory',exact:true}).click();
    await expect(stock.getByRole('button',{name:'Recover original request',exact:true})).toBeEnabled();
    await tabs.getByRole('link',{name:'Shopping',exact:true}).click();
    expect(await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'))).toBe(pending);
    await expect(note).toHaveValue(literal); expect(posts).toHaveLength(1);
    const original = page.waitForResponse(base + 'api/v1/inventory/requests/shopping.purchase/' + key).then(async receipt =>
      ({status:receipt.status(),body:await receipt.body()}));
    await recover.press('Enter'); const receipt = await original;
    expect(receipt.status).toBe(200); expect(JSON.parse(receipt.body.toString())).toMatchObject({operation_id:operation});
    await expect(shop.getByText('Purchase recorded.',{exact:true})).toBeVisible();
    // Recovery of a different command cannot clear this still-unsubmitted extra/session draft.
    await expect(note).toHaveValue(literal);
    await expect(list.getByRole('textbox',{name:'Extra item name',exact:true})).toHaveValue('Unsent extra');
    await expect(draftSession.getByRole('textbox',{name:'Store (optional)',exact:true})).toHaveValue('Unsent shop');
    expect(posts).toHaveLength(1); expect(await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'))).toBeNull();
    const after = await stats(); for(const table of ['receipts','audit','outbox']) expect(after.counts[table]).toBe(before.counts[table]+1);
    await info.attach('shopping-original-receipt',{body:receipt.body,contentType:'application/json'});
  });

  test(`inventory1-C04 (#162): current reader, requester and shopper grants with stale and denied reads in ${mode}`, async ({page,context,browser,request}) => {
    test.setTimeout(90_000);
    const {origin,base,tabs,shop} = await create(page,context,request,mode);
    await tabs.getByRole('link',{name:'Shopping',exact:true}).click();
    const note = shop.getByRole('textbox',{name:'Note (optional)',exact:true}); await note.fill('Retain through outage');
    const catalogPath = new URL(base + 'api/v1/inventory').pathname;
    await page.route(url => url.pathname === catalogPath,route => route.abort('failed'),{times:1});
    await shop.getByRole('button',{name:'Refresh Shopping',exact:true}).click();
    await expect(shop.getByText('This is the last loaded information. Your draft is retained. Refresh before making changes.',{exact:true})).toBeVisible();
    await expect(note).toHaveValue('Retain through outage'); await expect(note).toBeDisabled();
    await shop.getByRole('button',{name:'Refresh Shopping',exact:true}).click(); await expect(note).toBeEnabled();
    await page.route(url => url.pathname === catalogPath,route => route.fulfill({status:403,
      headers:{'Cache-Control':'no-store'},json:{state:'blocked',code:'permission_denied',message:'Denied.',
        action_required:'Refresh current household access.',correlation_id:'cor_shopping_navigation'}}),{times:1});
    await shop.getByRole('button',{name:'Refresh Shopping',exact:true}).click();
    await expect(shop.getByText('Current access to Inventory and Shopping was denied. Refresh your household access.',{exact:true})).toBeVisible();
    await expect(note).toHaveCount(0);
    await tabs.getByRole('link',{name:'Household',exact:true}).click();
    const admin = page.locator('domus-administration');
    await admin.getByRole('button',{name:'Edit access rules',exact:true}).click();
    await admin.getByLabel('HA administrator mapping',{exact:true}).selectOption('selected_ha_user');
    await admin.getByLabel('Target Home Assistant account',{exact:true}).selectOption('a'.repeat(32)); await save(admin);
    const peer = await browser.newContext(), other = await peer.newPage(), subject = mode === 'native' ? 'c' : 'b';
    try {
      if(mode === 'native') await peer.addCookies([{name:'ingress_session',value:'e'.repeat(128),domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
      else expect((await request.post(origin + '/__fixture__/identity',{data:{subject:subject.repeat(32)}})).ok()).toBe(true);
      await other.goto(base + '#household');
      if(mode === 'standalone') {
        await other.getByRole('button',{name:'Sign in with Home Assistant',exact:true}).click();
        await other.getByRole('link',{name:'Continue as fixture user',exact:true}).click();
      }
      await other.getByRole('button',{name:'Request membership',exact:true}).click();
      await expect(other.getByRole('heading',{name:'Membership pending',exact:true})).toBeVisible();
      if(mode === 'standalone') expect((await request.post(origin + '/__fixture__/identity',{data:{subject:'a'.repeat(32)}})).ok()).toBe(true);
      for(const role of ['viewer','restricted','adult'] as const) {
        await admin.getByRole('button',{name:'Refresh administration',exact:true}).click();
        await admin.getByRole('button',{name:'Manage participant: Fictional account '+subject,exact:true}).click();
        await admin.getByLabel('Household profile',{exact:true}).selectOption(role);
        if(role === 'viewer') {
          await admin.getByLabel('Membership status',{exact:true}).selectOption('active');
          await admin.getByRole('checkbox',{name:'Approve household access',exact:true}).check();
        }
        await admin.getByLabel('Manage inventory',{exact:true}).selectOption('deny'); await save(admin);
        await other.getByRole('button',{name:'Refresh status',exact:true}).click();
        await other.locator('vyp-ha-tabs').getByRole('link',{name:'Shopping',exact:true}).click();
        const otherShop = other.locator('domus-app #shopping');
        await expect(otherShop.getByRole('heading',{name:'Shopping',exact:true,level:2})).toBeVisible();
        await expect(otherShop.getByRole('textbox',{name:'Note (optional)',exact:true})).toHaveCount(role === 'viewer' ? 0 : 1);
        await otherShop.getByRole('button',{name:'Show purchases',exact:true}).click();
        await expect(otherShop.getByRole('button',{name:'Record purchase',exact:true})).toHaveCount(role === 'adult' ? 1 : 0);
        if(role === 'restricted') {
          await otherShop.getByRole('textbox',{name:'Extra item name',exact:true}).fill('Requested without Inventory grant');
          await otherShop.getByRole('textbox',{name:/^Extra quantity/u}).fill('1');
          await otherShop.getByRole('button',{name:'Add manual extra',exact:true}).click();
          await expect(otherShop.getByText('Manual extra added.',{exact:true})).toBeVisible();
        }
        if(role === 'adult') {
          await otherShop.getByRole('textbox',{name:'Untracked item name',exact:true}).fill('Bought without Inventory grant');
          await otherShop.getByRole('textbox',{name:'Quantity purchased',exact:true}).fill('1');
          await otherShop.getByRole('button',{name:'Record purchase',exact:true}).click();
          await expect(otherShop.getByText('Purchase recorded.',{exact:true})).toBeVisible();
        }
        await other.locator('vyp-ha-tabs').getByRole('link',{name:'Inventory',exact:true}).click();
        await expect(other.locator('domus-app #inventory').getByRole('button',{name:'Register product',exact:true})).toHaveCount(0);
      }
    } finally {await peer.close();}
  });

  test(`inventory1-C05 (#162): closing a protected Shopping view retires draft and pending owner in ${mode}`, async ({page,context,request}) => {
    const {base,tabs,shop,commands} = await create(page,context,request,mode);
    await tabs.getByRole('link',{name:'Shopping',exact:true}).click();
    await shop.getByRole('textbox',{name:'Extra item name',exact:true}).fill('Private interrupted extra');
    await shop.getByRole('textbox',{name:/^Extra quantity/u}).fill('1');
    await shop.getByRole('textbox',{name:'Note (optional)',exact:true}).fill('Private note');
    let posts = 0; const lookups:string[] = [];
    page.on('request', item => {
      if(item.url() === commands && item.method() === 'POST') posts++;
      if(item.url().startsWith(base + 'api/v1/inventory/requests/')) lookups.push(item.url());
    });
    await page.route(commands,route => route.abort('connectionclosed'));
    await shop.getByRole('button',{name:'Add manual extra',exact:true}).click();
    await expect(shop.getByRole('button',{name:'Check original operation',exact:true})).toBeEnabled();
    const packet = await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'));
    expect(packet).not.toBeNull();
    await expect(shop.getByRole('textbox',{name:'Note (optional)',exact:true})).toHaveValue('Private note');
    // A fresh composition must keep this same verified owner's original bytes
    // without a lookup or resend merely because the browser was reloaded.
    await page.reload();
    await expect(shop.getByRole('button',{name:'Check original operation',exact:true})).toBeEnabled();
    expect(await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'))).toBe(packet);
    expect(posts).toBe(1); expect(lookups).toEqual([]);
    await expect(shop.getByRole('textbox',{name:'Note (optional)',exact:true})).toBeDisabled();
    await page.getByRole('button',{name:mode === 'native' ? 'Close this view' : 'Sign out of Domus',exact:true}).click();
    await expect(page.getByRole('button',{name:mode === 'native' ? 'Reopen Domus' : 'Sign in with Home Assistant',exact:true})).toBeVisible();
    await expect(shop.getByRole('textbox',{name:'Note (optional)',exact:true})).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem('domus.inventory.v1'))).toBeNull();
    expect(posts).toBe(1); expect(lookups).toEqual([]);
  });

  test(`inventory1-C06 (#162): real restart and restore retain ledger and original receipt in ${mode}`, async ({page,context,request},info) => {
    test.setTimeout(60_000);
    const {origin,base,tabs,shop,stock,write,stats,headers} = await create(page,context,request,mode);
    const product = (await write('compatibility-product',{action:'inventory.register-product',name:'Compatibility tea',base_unit:'piece'})).result;
    await write('compatibility-intake',{action:'inventory.intake',product_id:product.product_id,quantity:'3'});
    const original = await write('compatibility-extra',{action:'shopping.add-extra',product_id:null,name:'Compatibility bags',quantity:'2',note:'Literal\nNote\t😀',priority:'high'});
    await stock.getByRole('button',{name:'Refresh inventory',exact:true}).click();
    await expect(stock.getByRole('article',{name:'Compatibility tea',exact:true}).locator('dd')).toHaveText(['3','0','3']);
    const before = await stats();
    expect((await request.post(origin + '/__fixture__/operator',{data:{action:'snapshot'}})).ok()).toBe(true);
    for(const action of ['restart','restore'] as const) {
      expect((await request.post(origin + '/__fixture__/operator',{data:{action}})).ok()).toBe(true);
      await page.goto(base + '#shopping'); await page.reload();
      if(mode === 'standalone') {
        const signIn = page.getByRole('button',{name:'Sign in with Home Assistant',exact:true});
        await expect(signIn.or(shop.getByRole('heading',{name:'Shopping',exact:true,level:2}))).toBeVisible();
        if(await signIn.isVisible()) {
          await signIn.click(); await page.getByRole('link',{name:'Continue as fixture user',exact:true}).click();
          await page.goto(base + '#shopping');
        }
      }
      await expect(shop.getByRole('heading',{name:'Shopping',exact:true,level:2})).toBeVisible();
      await expect(shop.locator('.manual-note')).toHaveText('Literal\nNote\t😀');
      const receipt = await page.request.get(base + 'api/v1/inventory/requests/shopping.add-extra/compatibility-extra',{headers});
      expect(receipt.status()).toBe(200); expect(await receipt.json()).toMatchObject({operation_id:original.operation_id,result:original.result});
      await tabs.getByRole('link',{name:'Inventory',exact:true}).click();
      await expect(stock.getByRole('article',{name:'Compatibility tea',exact:true}).locator('dd')).toHaveText(['3','0','3']);
      const after = await stats(); for(const table of ['receipts','audit','outbox','members','households']) expect(after.counts[table],table).toBe(before.counts[table]);
      await info.attach('compatibility-'+action,{body:await receipt.body(),contentType:'application/json'});
    }
  });
}
