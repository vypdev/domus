import {expect, test} from '@playwright/test';

test.use({hasTouch: true});

const ingress = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';

for (const mode of ['native', 'standalone'] as const) {
  test(`local barcode lookup and reviewed association recovery in ${mode}`, async ({page, context, request}, info) => {
    test.setTimeout(50_000);
    const origin = `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
    const base = origin + (mode === 'native' ? ingress : '') + '/';
    const barcode = '00036000291452';
    const commands = base + 'api/v1/inventory/commands';
    const lookup = base + 'api/v1/inventory/barcode?barcode=' + barcode;
    const external: string[] = [];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      external.push(route.request().url());
      return route.abort('internetdisconnected');
    });
    if (process.env.DOMUS_BROWSER_IMAGE) {
      const image = await request.get(origin + '/__fixture__/image');
      expect(image.ok()).toBe(true);
      expect(await image.json()).toEqual({source_commit:process.env.DOMUS_TEST_SOURCE_COMMIT,
        architecture:process.env.DOMUS_TEST_ARCH, image_id:expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode});
    }
    expect((await request.post(origin + '/__fixture__/reset')).ok()).toBe(true);
    if (mode === 'native') await context.addCookies([{name:'ingress_session', value:'f'.repeat(128),
      domain:'127.0.0.1', path:'/', httpOnly:true, sameSite:'Strict'}]);
    await page.goto(base + '#household');
    if (mode === 'standalone') {
      await page.getByRole('button', {name:'Sign in with Home Assistant', exact:true}).press('Enter');
      await page.getByRole('link', {name:'Continue as fixture user', exact:true}).press('Enter');
    }
    await page.getByRole('textbox', {name:'Household name', exact:true}).fill('Barcode QA household');
    await page.getByRole('textbox', {name:'Timezone', exact:true}).fill('UTC');
    await page.getByRole('button', {name:'Create household', exact:true}).press('Enter');
    await page.locator('vyp-ha-tabs').getByRole('link', {name:'Inventory', exact:true}).press('Enter');
    const stock = page.locator('domus-inventory');
    for (const name of ['QA barcode soap', 'QA barcode tea']) {
      await stock.getByRole('textbox', {name:'Product name', exact:true}).fill(name);
      await stock.getByRole('button', {name:'Register product', exact:true}).press('Enter');
      await expect(stock.getByRole('article', {name, exact:true})).toBeVisible();
    }
    const digits = stock.getByRole('textbox', {name:'Digits below the barcode', exact:true});
    await expect(digits).toHaveAttribute('type', 'text');
    await expect(digits).toHaveAttribute('inputmode', 'numeric');
    await digits.fill(barcode + '0');
    await digits.press('Enter');
    await expect(digits).toHaveValue(barcode + '0');
    await expect(digits).toBeFocused();
    await expect(stock.getByText('Enter 8, 12, 13 or 14 printed digits with a valid check digit.')).toBeVisible();
    await digits.fill('036000291452');
    await digits.press('Enter');
    await expect(stock.getByText('Unlinked barcode in this household.', {exact:true})).toBeVisible();
    await expect(stock.locator('.barcode-result')).toBeFocused();
    const firstProduct = stock.locator('.products > article').first();
    await page.keyboard.press('Tab');
    await expect(stock.getByRole('link', {name:'Choose a product in Pantry below.', exact:true})).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(firstProduct).toBeFocused();
    await stock.getByRole('button', {name:'Associate barcode with QA barcode soap', exact:true}).press('Enter');
    const review = stock.getByRole('form', {name:'Review barcode association', exact:true});
    await expect(review).toBeFocused();
    await expect(review).toContainText(barcode);
    let originalKey = '';
    let associationId = '';
    await page.route(commands, async route => {
      expect(route.request().postDataJSON()).toMatchObject({action:'inventory.link-barcode', barcode});
      originalKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0, maxRedirects:0});
      expect(committed.ok()).toBe(true);
      associationId = (await committed.json()).result.association_id;
      await route.abort('connectionclosed');
    });
    await review.getByRole('button', {name:'Confirm barcode association', exact:true}).press('Enter');
    await expect(stock.getByRole('button', {name:'Recover original request', exact:true})).toBeEnabled();
    await page.unroute(commands);
    await page.reload();
    const original = page.waitForResponse(base + 'api/v1/inventory/requests/inventory.link-barcode/' + originalKey);
    await stock.getByRole('button', {name:'Recover original request', exact:true}).press('Enter');
    expect((await original).ok()).toBe(true);
    await expect(stock.getByText('Barcode associated.', {exact:false})).toBeVisible();
    await expect(stock.getByText('Product found QA barcode soap', {exact:true})).toBeVisible();
    await expect(digits).toHaveValue(barcode);
    await expect(stock.getByRole('article', {name:'QA barcode soap', exact:true}).locator('dd')).toHaveText(['0', '0', '0']);
    await stock.getByRole('button', {name:'Open product stock', exact:true}).press('Enter');
    await expect(stock.getByRole('region', {name:'Movement history · QA barcode soap', exact:true})).toBeFocused();
    await stock.getByRole('button', {name:'Remove barcode association', exact:true}).press('Enter');
    const oldReview = stock.getByRole('form', {name:'Review barcode removal', exact:true});
    await expect(oldReview).toBeFocused();

    const peer = await context.newPage();
    await peer.goto(base + '#inventory');
    const other = peer.locator('domus-inventory');
    await other.getByRole('textbox', {name:'Digits below the barcode', exact:true}).fill('036000291452');
    await other.getByRole('button', {name:'Find product', exact:true}).press('Enter');
    await other.getByRole('button', {name:'Remove barcode association', exact:true}).press('Enter');
    await other.getByRole('button', {name:'Confirm barcode removal', exact:true}).press('Enter');
    await expect(other.getByText('Unlinked barcode in this household.', {exact:true})).toBeVisible();
    await other.getByRole('button', {name:'Associate barcode with QA barcode tea', exact:true}).press('Enter');
    await other.getByRole('button', {name:'Confirm barcode association', exact:true}).press('Enter');
    await expect(other.getByText('Product found QA barcode tea', {exact:true})).toBeVisible();
    const stale = page.waitForRequest(item => item.url() === commands && item.method() === 'POST');
    await oldReview.getByRole('button', {name:'Confirm barcode removal', exact:true}).press('Enter');
    expect((await stale).postDataJSON()).toMatchObject({action:'inventory.remove-barcode', barcode, association_id:associationId});
    await expect(stock.getByText('The association changed. Review the current product before confirming again.', {exact:true})).toBeVisible();
    await expect(stock.getByText('Product found QA barcode tea', {exact:true})).toBeVisible();
    await expect(oldReview).toHaveCount(0);
    await stock.screenshot({path:info.outputPath('barcode-en-keyboard.png')});
    await peer.close();

    await page.setViewportSize({width:390, height:844});
    await page.emulateMedia({colorScheme:'dark', reducedMotion:'reduce'});
    await page.getByRole('combobox', {name:'Language', exact:true}).selectOption('es');
    const spanish = stock.getByRole('textbox', {name:'Dígitos bajo el código de barras', exact:true});
    const searchCard = stock.getByRole('article', {name:'Buscar producto por código de barras', exact:true});
    await expect(searchCard).toHaveCSS('background-color', 'rgb(24, 36, 47)');
    await expect(searchCard).toHaveCSS('color', 'rgb(237, 244, 250)');
    await expect(stock.getByRole('button', {name:'Buscar producto', exact:true})).toHaveCSS('color', 'rgb(24, 36, 47)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await spanish.fill('036000291452');
    await page.route(lookup, route => route.abort('failed'), {times:1});
    await stock.getByRole('button', {name:'Buscar producto', exact:true}).tap();
    await expect(stock.getByText('La búsqueda local del código no está disponible. Reintenta la búsqueda o actualiza Inventario.', {exact:true})).toBeVisible();
    await expect(spanish).toHaveValue('036000291452');
    await expect(stock.getByRole('button', {name:'Reintentar búsqueda del código', exact:true})).toBeFocused();
    await stock.getByRole('button', {name:'Reintentar búsqueda del código', exact:true}).tap();
    await expect(stock.getByText('Producto encontrado QA barcode tea', {exact:true})).toBeVisible();
    await expect(stock.locator('.barcode-result')).toBeFocused();
    await stock.getByRole('button', {name:'Eliminar asociación del código', exact:true}).tap();
    await stock.getByRole('button', {name:'Confirmar retirada del código', exact:true}).tap();
    await expect(stock.getByText('Código sin asociación en este hogar.', {exact:true})).toBeVisible();
    await expect(spanish).toHaveValue('036000291452');
    await stock.screenshot({path:info.outputPath('barcode-es-touch.png')});
    expect(external).toEqual([]);
  });
}

for (const mode of ['native', 'standalone'] as const) {
  test(`shared workspace navigation in ${mode}`, async ({page, context, request}, info) => {
    test.setTimeout(75_000);
    const origin = `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
    const base = origin + (mode === 'native' ? ingress : '') + '/';
    if (process.env.DOMUS_BROWSER_IMAGE) {
      const image = await request.get(origin + '/__fixture__/image');
      expect(image.ok()).toBe(true);
      expect(await image.json()).toEqual({
        source_commit: process.env.DOMUS_TEST_SOURCE_COMMIT,
        architecture: process.env.DOMUS_TEST_ARCH,
        image_id: expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode,
      });
    }
    expect((await request.post(origin + '/__fixture__/reset')).ok()).toBe(true);
    const writes: string[] = [];
    page.on('request', item => {
      if (item.url().startsWith(base + 'api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(item.method()))
        writes.push(item.method() + ' ' + item.url());
    });
    if (mode === 'native')
      await context.addCookies([{name: 'ingress_session', value: 'f'.repeat(128), domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
    await page.goto(base + '#household');
    const tabs = page.locator('vyp-ha-tabs');
    await expect(tabs).toHaveCount(0);
    if (mode === 'standalone') {
      await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
      await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
    }
    const name = page.getByLabel('Household name', {exact: true});
    await expect(name).toBeVisible();
    await expect(tabs).toHaveCount(0);
    await name.fill('Maple House');
    await page.getByLabel('Timezone', {exact: true}).fill('UTC');
    await page.getByRole('button', {name: 'Create household', exact: true}).click();

    const administration = page.locator('domus-administration');
    const overview = tabs.getByRole('link', {name: 'Overview', exact: true});
    const tasks = tabs.getByRole('link', {name: 'Tasks', exact: true});
    const calendar = tabs.getByRole('link', {name: 'Calendar', exact: true});
    const family = tabs.getByRole('link', {name: 'Family', exact: true});
    const familyRegion = page.locator('domus-app #family');
    const inventory = tabs.getByRole('link', {name: 'Inventory', exact: true});
    const stock = page.locator('domus-app #inventory');
    const reopenInventory = async (locale: 'en' | 'es') => {
      await page.reload();
      await expect(page).toHaveURL(base + '#inventory');
      await expect(stock.getByRole('button', {
        name:/^(Recover original request|Recuperar la solicitud original)$/u,
      })).toBeEnabled();
      await page.getByRole('combobox', {name:/^(Language|Idioma)$/u}).selectOption(locale);
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
    };
    const household = tabs.getByRole('link', {name: 'Household', exact: true});
    const overviewRegion = page.locator('domus-app #overview');
    const tasksRegion = page.locator('domus-app #tasks');
    const calendarRegion = page.locator('domus-app #calendar');
    const householdRegion = page.locator('domus-app #household');
    if (mode === 'standalone') await household.click();
    await expect(administration.getByRole('button', {name: 'Edit own alias', exact: true})).toBeEnabled();
    await expect(tabs.getByRole('navigation', {name: 'Household navigation'})).toBeVisible();
    await expect(overview).toHaveAttribute('href', '#overview');
    await expect(tasks).toHaveAttribute('href', '#tasks');
    await expect(calendar).toHaveAttribute('href', '#calendar');
    await expect(family).toHaveAttribute('href', '#family');
    await expect(inventory).toHaveAttribute('href', '#inventory');
    await expect(household).toHaveAttribute('href', '#household');
    await expect(household).toHaveCSS('height', '56px');
    await overview.click();
    await expect(page).toHaveURL(base + '#overview');
    await expect(overviewRegion).toBeFocused();
    await expect(overview).toHaveAttribute('aria-current', 'page');
    await expect(overview).toHaveCSS('border-bottom-width', '2px');
    await tabs.screenshot({path: info.outputPath('en-light-wide.png')});
    await expect(overviewRegion.getByRole('heading', {name:'Assigned to me · 0', exact:true})).toBeVisible();
    await expect(overviewRegion.getByRole('heading', {name:'Unclaimed tasks · 0', exact:true})).toBeVisible();

    await overview.focus();
    await page.keyboard.press('Tab');
    await expect(tasks).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(base + '#tasks');
    await expect(tasksRegion).toBeFocused();
    await expect(tasks).toHaveAttribute('aria-current', 'page');
    await expect(administration).toBeHidden();
    await expect(page.getByRole('button', {name: 'Create task', exact: true})).toBeEnabled();
    await page.goBack();
    await expect(overview).toHaveAttribute('aria-current', 'page');
    await page.goForward();
    await expect(tasks).toHaveAttribute('aria-current', 'page');
    await tasks.focus();
    await page.keyboard.press('Tab');
    await expect(calendar).toBeFocused();
    expect((await request.post(origin + '/__fixture__/revision', {
      data:{revision:'9007199254740993',calendar:true},
    })).ok()).toBe(true);
    const reading = page.waitForResponse(response => response.url().startsWith(base + 'api/v1/tasks/calendar?'));
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(base + '#calendar');
    await expect(calendarRegion).toBeFocused();
    await expect(calendar).toHaveAttribute('aria-current', 'page');
    expect((await reading).ok()).toBe(true);
    await expect(calendarRegion.getByText('There are no matching entries in this range.')).toBeVisible();
    await expect(calendarRegion.getByLabel('My week starts on')).toHaveValue('monday');
    await page.goBack();
    await expect(tasks).toHaveAttribute('aria-current', 'page');
    await page.goForward();
    await expect(calendar).toHaveAttribute('aria-current', 'page');
    await calendar.focus();
    await page.keyboard.press('Tab');
    await expect(family).toBeFocused();
    const familyRead = page.waitForResponse(response => response.url().startsWith(base + 'api/v1/family?'));
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(base + '#family');
    await expect(familyRegion).toBeFocused();
    await expect(family).toHaveAttribute('aria-current', 'page');
    const firstFamily = await familyRead;
    expect(firstFamily.ok()).toBe(true);
    await expect(familyRegion.getByText('Available balance', {exact: true})).toBeVisible();
    await expect(familyRegion.getByText('There are no points movements yet.')).toBeVisible();
    const rewards = familyRegion.locator('domus-rewards');
    await expect(rewards.getByText('Rewards are disabled for this household.')).toBeVisible();
    await family.focus();
    await page.keyboard.press('Tab');
    await expect(inventory).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(stock).toBeFocused();
    await expect(stock.getByText('There are no registered products.')).toBeVisible();
    await expect(stock.getByRole('article', {name:'Pantry', exact:true})).toHaveCSS('background-color', 'rgb(255, 255, 255)');
    await inventory.focus();
    await page.keyboard.press('Tab');
    await expect(household).toBeFocused();
    await expect(household.locator('[part=content]')).toHaveCSS('outline-style', 'solid');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(base + '#household');
    await expect(householdRegion).toBeFocused();
    await expect(household).toHaveAttribute('aria-current', 'page');
    await household.focus();
    await page.keyboard.press('Enter');
    await expect(householdRegion).toBeFocused();

    await administration.getByRole('button', {name: 'Edit own alias', exact: true}).click();
    await administration.getByRole('checkbox', {name: 'Use Home Assistant name', exact: true}).uncheck();
    const draft = administration.getByRole('textbox', {name: 'Domus alias', exact: true});
    await draft.fill('Unsubmitted household draft');
    await overview.click();
    await expect(page).toHaveURL(base + '#overview');
    await page.goBack();
    await expect(household).toHaveAttribute('aria-current', 'page');
    await expect(draft).toHaveValue('Unsubmitted household draft');
    await page.goForward();
    await expect(overview).toHaveAttribute('aria-current', 'page');
    await household.click();
    await page.reload();
    await expect(page).toHaveURL(base + '#household');
    await expect(household).toHaveAttribute('aria-current', 'page');
    await expect(householdRegion).toBeFocused();
    await expect(draft).toHaveCount(0);
    await expect(administration.getByRole('button', {name: 'Edit own alias', exact: true})).toBeEnabled();
    expect(writes).toEqual(['POST ' + base + 'api/v1/household']);

    await page.evaluate(() => {location.hash = 'household%2Funknown';});
    await expect(page).toHaveURL(base + '#household%2Funknown');
    await expect(overview).toHaveAttribute('aria-current', 'page');
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    await page.setViewportSize({width: 320, height: 720});
    await page.emulateMedia({colorScheme: 'dark', reducedMotion: 'reduce'});
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    await expect(tabs.getByRole('navigation', {name: 'Navegación del hogar'})).toBeVisible();
    const inicio = tabs.getByRole('link', {name: 'Inicio', exact: true});
    const hogar = tabs.getByRole('link', {name: 'Hogar', exact: true});
    await expect(tabs.getByRole('link', {name: 'Tareas', exact: true})).toBeVisible();
    await expect(inicio).toHaveAttribute('aria-current', 'page');
    await expect(tabs.locator('[part=frame]')).toHaveCSS('background-color', 'rgb(24, 36, 47)');
    await tabs.screenshot({path: info.outputPath('es-dark-narrow.png')});

    await tabs.getByRole('link', {name: 'Calendario', exact: true}).click();
    await expect(calendarRegion).toBeFocused();
    await expect(calendarRegion.getByText('No hay entradas que coincidan en este intervalo.')).toBeVisible();
    await calendarRegion.getByLabel('Vista del calendario').selectOption('agenda');
    await calendarRegion.getByRole('button', {name: 'Mostrar calendario'}).click();
    await expect(calendarRegion.getByText('Entradas que coinciden 0. Tareas que coinciden 0')).toBeVisible();
    await expect(calendarRegion.locator('.calendar-grid')).toHaveCount(0);
    await expect(calendarRegion.getByRole('combobox', {name:'Categoría', exact:true})).toHaveValue('');

    const pref = base + 'api/v1/tasks/calendar/preferences';
    const choose = calendarRegion.getByLabel('Mi semana empieza el');
    const recover = calendarRegion.getByRole('button', {name:'Consultar el cambio original de inicio de semana'});
    await expect(choose).toBeEnabled();
    let originalKey = '';
    await page.route(pref, async route => {
      if (route.request().method() !== 'PUT') {await route.continue(); return;}
      originalKey = route.request().headers()['idempotency-key'];
      expect(route.request().postData()).toBe('{"expected_revision":9007199254740993,"week_start":"sunday"}');
      const committed = await route.fetch();
      expect(committed.status()).toBe(200);
      // Capture exact bytes from the real reply before deliberately dropping its browser delivery.
      expect(await committed.text()).toContain('"revision":9007199254740994');
      await route.abort('connectionclosed');
    });
    await choose.selectOption('sunday');
    await expect(recover).toBeEnabled();
    await expect(calendarRegion.getByRole('alert')).toContainText('El cambio está sin confirmar');
    await page.reload();
    const recovered = calendarRegion.getByRole('button', {name:'Check original week-start change'});
    await expect(recovered).toBeEnabled();
    const originalReads: string[] = [];
    await page.route(pref + '/requests/' + originalKey, async route => {
      expect(route.request().method()).toBe('GET');
      // Retain upstream bytes before Chromium can discard its response body.
      const response = await route.fetch({maxRetries: 0, maxRedirects: 0});
      expect(response.status()).toBe(200);
      const body = await response.body();
      originalReads.push(body.toString('utf8'));
      await route.fulfill({response, body});
    });
    await recovered.click();
    await expect(recovered).toHaveCount(0);
    await expect(calendarRegion.getByLabel('My week starts on')).toHaveValue('sunday');
    expect(originalReads).toHaveLength(1);
    expect(originalReads[0]).toContain('"revision":9007199254740994');
    expect(writes).toEqual(['POST ' + base + 'api/v1/household', 'PUT ' + pref]);
    await page.getByLabel('Language', {exact: true}).selectOption('es');

    // Use the compiled application's current session and the real Points worker.
    const contextHeader = (await firstFamily.request().allHeaders())['x-domus-context'];
    expect(contextHeader).toBeTruthy();
    const access = await page.request.get(base + 'api/v1/tasks/access');
    expect(access.ok()).toBe(true);
    const member = (await access.json()).member_id;
    const csrf = await page.request.get(base + 'api/v1/auth/csrf');
    expect(csrf.ok()).toBe(true);
    const token = (await csrf.json()).csrf_token;
    const post = async (suffix: string, key: string, data: object) => {
      const response = await page.request.post(base + 'api/v1/tasks/' + suffix, {data, headers: {
        Origin: origin, 'X-Domus-Context': contextHeader, 'X-CSRF-Token': token, 'Idempotency-Key': key,
      }});
      expect(response.ok(), await response.text()).toBe(true);
      return (await response.json()).result;
    };
    const previousTaskViewport = page.viewportSize()!;
    await page.setViewportSize({width: 1120, height: 900});
    await page.emulateMedia({colorScheme: 'light'});
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await tabs.getByRole('link', {name: 'Tasks', exact: true}).click();
    const newTask = tasksRegion.locator('details.new-task:has(#new-task-title)');
    await expect(newTask).toBeVisible();
    if (!await newTask.evaluate((element: HTMLDetailsElement) => element.open))
      await newTask.locator('summary').press('Enter');
    await newTask.getByRole('textbox', {name: 'Title', exact: true}).fill('Water plants');
    const englishPoints = newTask.getByRole('textbox', {name: 'Base points (optional)', exact: true});
    await expect(englishPoints).toHaveAttribute('inputmode', 'decimal');
    await englishPoints.fill('2.251');
    await englishPoints.press('Enter');
    const basePointsError = newTask.getByText('Enter 0 to 10,000 points with up to two decimal places.');
    await expect(basePointsError).toBeVisible();
    await expect(basePointsError).toHaveCSS('color', 'rgb(120, 67, 7)');
    await expect(englishPoints).toBeFocused();
    await newTask.screenshot({path: info.outputPath('task-base-points-en-invalid.png')});
    await page.setViewportSize({width: 390, height: 820});
    await page.emulateMedia({colorScheme: 'dark'});
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    const spanishPoints = newTask.getByRole('textbox', {name: 'Puntos base (opcional)', exact: true});
    await expect(spanishPoints).toHaveAttribute('inputmode', 'decimal');
    await expect(spanishPoints).toHaveValue('2.251');
    await spanishPoints.tap();
    await spanishPoints.fill('2,25');
    await expect(spanishPoints).toHaveCSS('color', 'rgb(237, 244, 250)');
    await expect(newTask.getByText('Déjalo vacío para usar el valor predeterminado del hogar.'))
      .toHaveCSS('color', 'rgb(187, 203, 216)');
    await newTask.locator('#task-base-points').screenshot({path: info.outputPath('task-base-points-es-narrow.png')});
    const creationUrl = base + 'api/v1/tasks/definitions';
    const creation: {saved?: {occurrence_id: string; revision: number; point_value_minor: number}} = {};
    await page.route(creationUrl, async route => {
      if (route.request().method() !== 'POST') {await route.continue(); return;}
      expect(route.request().postDataJSON()).toMatchObject({title: 'Water plants', overrides: {point_value_minor: 225}});
      const committed = await route.fetch({maxRetries: 0, maxRedirects: 0});
      expect(committed.ok(), await committed.text()).toBe(true);
      creation.saved = (await committed.json()).result;
      await route.abort('connectionclosed');
    });
    await newTask.getByRole('button', {name: 'Crear tarea', exact: true}).tap();
    await expect(tasksRegion.getByText('Resultado sin confirmar', {exact: true})).toBeVisible();
    await expect(spanishPoints).toHaveValue('2,25');
    await page.unroute(creationUrl);
    const recoverCreation = tasksRegion.getByRole('region', {name: 'Solicitudes guardadas', exact: true})
      .getByRole('button', {name: 'Comprobar solicitud guardada', exact: true});
    await recoverCreation.click();
    await expect(tasksRegion.getByText('Cambio de tarea guardado', {exact: true})).toBeVisible();
    await expect(tasksRegion.getByRole('status').getByText('2,25', {exact: true})).toBeVisible();
    const seeded = creation.saved;
    if (seeded?.point_value_minor !== 225) throw Error('The original configured task was not saved');
    await page.setViewportSize(previousTaskViewport);
    const done = await post('occurrences/' + seeded.occurrence_id + '/complete', 'family-completed', {
      expected_revision: seeded.revision, performer_ids: [member], performed_at: Date.now() - 500,
    });
    const ledger = async () => {
      const result = await page.request.get(firstFamily.url(), {headers: {'X-Domus-Context': contextHeader}});
      if (result.status() === 503) {
        expect((await result.json()).code).toBe('storage_busy');
        return null;
      }
      expect(result.ok(), await result.text()).toBe(true);
      return result.json();
    };
    await expect.poll(async () => (await ledger())?.available_minor, {timeout: 15_000}).toBe(225);
    const participation = overviewRegion.locator('domus-family-overview');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await expect(participation.getByRole('heading',{name:'Tu participación esta semana',exact:true})).toBeVisible();
    await expect(participation.locator('dd')).toHaveText(['1','2,25']);
    await expect(participation.getByRole('article')).toHaveCSS('background-color','rgb(24, 36, 47)');
    await participation.screenshot({path:info.outputPath('family-overview-es-narrow.png')});
    await participation.getByRole('link',{name:'Abrir Familia',exact:true}).tap();
    await expect(familyRegion).toBeFocused();
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    await page.route(base + 'api/v1/family/overview', route => route.abort('failed'), {times:1});
    await overview.press('Enter');
    await expect(page).toHaveURL(base + '#overview');
    await expect(participation.getByText('Weekly participation could not be loaded.',{exact:true})).toBeVisible();
    await expect(overviewRegion.getByRole('heading',{name:/^Products below minimum ·/u})).toBeVisible();
    await participation.getByRole('button',{name:'Retry participation summary',exact:true}).press('Enter');
    await expect(participation.locator('dd')).toHaveText(['1','2.25']);
    await expect(participation.getByRole('article')).toHaveCSS('background-color','rgb(255, 255, 255)');
    await participation.screenshot({path:info.outputPath('family-overview-en-wide.png')});
    await participation.getByRole('link',{name:'Open Family',exact:true}).press('Enter');
    await expect(familyRegion).toBeFocused();
    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:320,height:720});
    await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
    await expect(familyRegion.getByText('Saldo disponible', {exact: true})).toBeVisible();
    await expect(familyRegion.getByText('Premio 2,25', {exact: true})).toBeVisible();
    await expect(familyRegion.getByText('Puntos estimados pendientes de verificación')).toBeVisible();
    await expect(familyRegion.getByText('Puntos estimados pendientes de registro')).toBeVisible();
    await familyRegion.getByRole('combobox', {name: 'Período', exact: true}).selectOption('month');
    const monthly = page.waitForResponse(response => response.url().startsWith(base + 'api/v1/family?'));
    await familyRegion.getByRole('button', {name: 'Mostrar participación'}).click();
    expect((await monthly).ok()).toBe(true);
    await expect(familyRegion.getByText(/UTC/u)).toBeVisible();
    await post('occurrences/' + seeded.occurrence_id + '/reopen', 'family-reopened', {
      expected_revision: done.revision, cycle_id: done.cycle.cycle_id, reason: 'Check the original work',
    });
    await expect.poll(async () => (await ledger())?.history.length, {timeout: 15_000}).toBe(2);
    await familyRegion.getByRole('button', {name: 'Actualizar', exact: true}).click();
    await expect(familyRegion.getByText('Reversión −2,25', {exact: true})).toBeVisible();
    await expect(familyRegion.getByText('Premio original', {exact: true})).toBeVisible();
    await familyRegion.screenshot({path: info.outputPath('family-es-reversal.png')});
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await expect(familyRegion.getByText('Reversal −2.25', {exact: true})).toBeVisible();
    await familyRegion.screenshot({path: info.outputPath('family-en-reversal.png')});
    await page.getByLabel('Language', {exact: true}).selectOption('es');

    const settings = familyRegion.locator('domus-allocation-settings');
    await expect(settings.getByRole('article')).toHaveCSS('background-color', 'rgb(24, 36, 47)');
    await expect(settings.getByRole('article')).toHaveCSS('color', 'rgb(237, 244, 250)');
    await settings.getByRole('combobox', {name: 'Política', exact: true}).selectOption('equal_share');
    await settings.getByRole('combobox', {name: 'Redondeo', exact: true}).selectOption('ceil');
    await settings.getByRole('button', {name: 'Guardar política', exact: true}).click();
    await expect(settings.getByText('Política de puntos guardada.', {exact: true})).toBeVisible();
    await tabs.getByRole('link', {name: 'Tareas', exact: true}).click();
    await tasksRegion.getByRole('button', {name: 'Actualizar tareas', exact: true}).click();
    await tasksRegion.getByRole('button', {name: 'Water plants', exact: true}).click();
    const taskSettings = tasksRegion.locator('domus-allocation-settings');
    await expect(taskSettings.getByRole('article')).toHaveCSS('background-color', 'rgb(24, 36, 47)');
    await expect(taskSettings.getByRole('article')).toHaveCSS('color', 'rgb(237, 244, 250)');
    const points = tasksRegion.locator('domus-allocation-preview');
    await points.locator('summary').click();
    await points.getByRole('button', {name: 'Previsualizar puntos', exact: true}).click();
    await expect(points.getByText('Total efectivo', {exact: true})).toBeVisible();
    await expect(points.getByText('2,25', {exact: true})).toBeVisible();
    await expect(points.getByText(/respecto al valor base/u)).toBeVisible();
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await expect(points.getByText('Actual total', {exact: true})).toBeVisible();
    await expect(points.getByText('2.25', {exact: true})).toBeVisible();
    await tasksRegion.getByRole('button', {name: 'Mark done now', exact: true}).click();
    await expect.poll(async () => (await ledger())?.available_minor, {timeout: 15_000}).toBe(300);
    await family.click();
    const details = familyRegion.locator('ol li').first().locator('summary');
    await details.click();
    await expect(familyRegion.getByText(/Equal shares.*Round up.*Policy revision 1/su)).toBeVisible();
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    await expect(familyRegion.getByText(/Cuotas iguales.*Hacia arriba.*Revisión de la política 1/su)).toBeVisible();

    await expect(rewards.getByText('Las recompensas están desactivadas para este hogar.')).toBeVisible();
    await rewards.getByRole('button', {name: 'Activar recompensas'}).click();
    await expect(rewards.getByRole('button', {name: 'Desactivar recompensas'})).toBeVisible();
    await rewards.getByRole('textbox', {name: 'Nombre de la recompensa'}).fill('Movie night');
    await rewards.getByRole('textbox', {name: 'Precio en puntos'}).fill('2,00');
    await rewards.getByRole('button', {name: 'Guardar recompensa'}).click();
    await rewards.getByRole('button', {name: 'Solicitar recompensa'}).click();
    await expect(rewards.getByText('Disponible después de la reserva 1,00')).toBeVisible();
    await rewards.getByRole('button', {name: 'Confirmar solicitud'}).click();
    await rewards.getByRole('button', {name: 'Cancelar solicitud', exact: true}).click();
    await rewards.getByRole('textbox', {name: 'Motivo de la cancelación'}).fill('Choose a different day');
    await rewards.getByRole('button', {name: 'Confirmar cancelación'}).click();
    await expect(rewards.getByText(/Choose a different day/u)).toBeVisible();
    await rewards.getByRole('button', {name: 'Solicitar recompensa'}).click();
    await rewards.getByRole('button', {name: 'Confirmar solicitud'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Pendiente de aprobación'})).toBeVisible();
    const code = await rewards.locator('li').filter({hasText: 'Pendiente de aprobación'}).locator('code').textContent();
    await rewards.getByRole('textbox', {name: 'Código de solicitud', exact: true}).fill(code!);
    await rewards.getByRole('button', {name: 'Aprobar solicitud'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Aprobada para entrega'})).toBeVisible();
    await expect.poll(async () => (await ledger())?.reserved_minor).toBe(200);
    const latest = await (await page.request.get(base + 'api/v1/tasks/occurrences/' + seeded.occurrence_id,
      {headers: {'X-Domus-Context': contextHeader}})).json();
    await post('occurrences/' + seeded.occurrence_id + '/reopen', 'family-reward-hold', {
      expected_revision: latest.work.revision, cycle_id: latest.cycle.cycle_id, reason: 'Check the reward funding',
    });
    await expect.poll(async () => (await ledger())?.available_minor, {timeout: 15_000}).toBe(-200);
    await rewards.getByRole('button', {name: 'Actualizar recompensas'}).click();
    await expect(rewards.getByText('Puntos necesarios para cubrir las reservas activas 2,00')).toBeVisible();
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await expect(rewards.getByText('Points needed to cover active reservations 2.00')).toBeVisible();
    await rewards.getByRole('checkbox', {name: 'I delivered this reward'}).check();
    await rewards.getByRole('button', {name: 'Record delivery'}).click();
    await expect(rewards.getByText('Delivery is paused until available points cover the reservation.')).toBeVisible();

    const newCredit = await post('definitions', 'family-reward-credit', {
      title: 'Organize shelves', overrides: {point_value_minor: 300},
    });
    const earned = await post('occurrences/' + newCredit.occurrence_id + '/complete', 'family-reward-completed', {
      expected_revision: newCredit.revision, performer_ids: [member], performed_at: Date.now() - 500,
    });
    await expect.poll(async () => (await ledger())?.available_minor, {timeout: 15_000}).toBe(100);
    await rewards.getByRole('button', {name: 'Refresh rewards'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Approved for delivery'})).toBeVisible();
    await expect.poll(async () => (await ledger())?.spending_count).toBe(0);
    await rewards.getByRole('checkbox', {name: 'I delivered this reward'}).check();
    await rewards.getByRole('button', {name: 'Record delivery'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Spending recorded'})).toBeVisible();
    await expect(familyRegion.getByText('Spent in this period 2.00')).toBeVisible();
    await post('occurrences/' + newCredit.occurrence_id + '/reopen', 'family-reward-negative', {
      expected_revision: earned.revision, cycle_id: earned.cycle.cycle_id, reason: 'Check the original work',
    });
    await expect.poll(async () => (await ledger())?.posted_minor, {timeout: 15_000}).toBe(-200);
    await familyRegion.getByRole('button', {name: 'Refresh', exact: true}).click();
    await expect(familyRegion.getByText(/Task reversals can leave a negative posted balance/u)).toBeVisible();
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    await expect(familyRegion.getByText('Gastado en este período 2,00')).toBeVisible();
    await expect(rewards.locator('li').filter({hasText: 'Gasto registrado'})).toBeVisible();

    await tabs.getByRole('link', {name: 'Inventario', exact: true}).click();
    await expect(stock).toBeFocused();
    await expect(stock.getByText('No hay productos registrados.')).toBeVisible();
    const pantry = stock.getByRole('article', {name:'Despensa', exact:true});
    await expect(pantry).toHaveCSS('background-color', 'rgb(24, 36, 47)');
    await expect(pantry).toHaveCSS('color', 'rgb(237, 244, 250)');
    await expect(stock.getByRole('button', {name:'Registrar producto'})).toHaveCSS('color', 'rgb(24, 36, 47)');
    await stock.getByRole('textbox', {name: 'Nombre del producto'}).fill('Pantry oil');
    await stock.getByRole('combobox', {name: 'Unidad base'}).selectOption('millilitre');
    await stock.getByRole('button', {name: 'Registrar producto'}).click();
    const oil = stock.getByRole('article', {name: 'Pantry oil'});
    await expect(oil.getByText('Stock disponible')).toBeVisible();
    await oil.getByRole('button', {name: 'Registrar entrada de stock'}).click();
    await oil.getByRole('textbox', {name: 'Cantidad que se añadirá'}).fill('0');
    await oil.getByRole('button', {name: 'Revisar entrada'}).click();
    await expect(oil.getByRole('alert')).toContainText('Introduce una cantidad');
    await oil.getByRole('textbox', {name: 'Cantidad que se añadirá'}).fill('1,250001');
    await oil.getByRole('button', {name: 'Revisar entrada'}).click();
    await expect(oil.getByText('Pantry oil · 1,250001 mililitros.', {exact:false})).toBeVisible();
    const inventoryCommands = base + 'api/v1/inventory/commands';
    let intakeKey: string | undefined;
    await page.route(inventoryCommands, async route => {
      intakeKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      expect((await committed.json()).result.quantity).toBe('1.250001');
      await route.abort('connectionclosed');
    });
    await oil.getByRole('button', {name: 'Confirmar entrada'}).click();
    await expect(stock.getByText(/El resultado está sin confirmar/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('es');
    expect(intakeKey).toBeTruthy();
    const originalIntake = page.waitForResponse(base + 'api/v1/inventory/requests/inventory.intake/' + intakeKey);
    await stock.getByRole('button', {name: 'Recuperar la solicitud original'}).click();
    expect((await originalIntake).ok()).toBe(true);
    await expect(stock.getByText('Stock registrado en la despensa. 1,250001 mililitros')).toBeVisible();
    await expect(oil.locator('dd')).toHaveText(['1,250001', '0', '1,250001']);
    await stock.getByRole('link', {name: 'Ver producto'}).click();
    await expect(oil).toBeFocused();
    await stock.getByText('Detalles del comprobante').click();
    await expect(stock.getByText('Movimiento de stock', {exact:false})).toBeVisible();
    await stock.screenshot({path:info.outputPath('inventory-es-intake.png')});
    await page.getByLabel('Idioma', {exact:true}).selectOption('en');
    await expect(stock.getByText('Stock recorded in Pantry. 1.250001 millilitres')).toBeVisible();
    await expect(oil.locator('dd')).toHaveText(['1.250001', '0', '1.250001']);
    await stock.screenshot({path:info.outputPath('inventory-en-intake.png')});
    await oil.getByRole('button', {name:'Show movement history'}).click();
    const history = stock.getByRole('region', {name:'Movement history · Pantry oil'});
    await expect(history).toBeFocused();
    await expect(history.getByText('+1.250001 millilitres')).toBeVisible();
    await expect(history.getByText('Author')).toBeVisible();
    await expect(history.getByText('Date')).toBeVisible();

    await page.getByLabel('Language', {exact:true}).selectOption('es');
    const historial = stock.getByRole('region', {name:'Historial de movimientos · Pantry oil'});
    await expect(historial.getByText('+1,250001 mililitros')).toBeVisible();
    await historial.getByRole('button', {name:'Revertir esta entrada'}).click();
    await expect(historial.getByRole('textbox', {name:'Motivo'})).toBeFocused();
    await historial.getByRole('button', {name:'Confirmar reversión de entrada'}).click();
    await expect(historial.getByRole('alert')).toContainText('Introduce un motivo');
    await historial.getByRole('textbox', {name:'Motivo'}).fill('Entrada duplicada');
    let correctionKey = '';
    let originalMovement = '';
    let compensatingMovement = '';
    await page.route(inventoryCommands, async route => {
      correctionKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      const {result} = await committed.json();
      expect(result.quantity).toBe('-1.250001');
      originalMovement = result.corrects;
      compensatingMovement = result.movement_id;
      await route.abort('connectionclosed');
    });
    await historial.getByRole('button', {name:'Confirmar reversión de entrada'}).click();
    await expect(stock.getByText(/El resultado está sin confirmar/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('en');
    const originalCorrection = page.waitForResponse(
      base + 'api/v1/inventory/requests/inventory.correct-intake/' + correctionKey,
    );
    await stock.getByRole('button', {name:'Recover original request'}).click();
    expect((await originalCorrection).ok()).toBe(true);
    await expect(stock.getByText('Intake reversed. -1.250001 millilitres')).toBeVisible();
    await expect(oil.locator('dd')).toHaveText(['0', '0', '0']);
    await oil.getByRole('button', {name:'Show movement history'}).click();
    const compensation = history.getByRole('listitem').filter({hasText:'Intake correction'});
    const original = history.getByRole('listitem').filter({hasText:'Stock intake'});
    await expect(compensation).toContainText('-1.250001 millilitres');
    await expect(compensation).toContainText('Entrada duplicada');
    await expect(original).toContainText('+1.250001 millilitres');
    await expect(original.getByRole('button', {name:'Reverse this intake'})).toHaveCount(0);
    await compensation.getByText('Movement details').click();
    await expect(compensation.getByText('Original movement ' + originalMovement)).toBeVisible();
    await original.getByText('Movement details').click();
    await expect(original.getByText('Compensating movement ' + compensatingMovement)).toBeVisible();

    await history.getByRole('button', {name:'Adjust stock'}).click();
    await history.getByRole('textbox', {name:'Signed adjustment quantity'}).fill('+2.000001');
    await history.getByRole('textbox', {name:'Reason'}).fill('Physical count');
    await history.getByRole('button', {name:'Save adjustment'}).click();
    await expect(oil.locator('dd')).toHaveText(['2.000001', '0', '2.000001']);
    await expect(history.getByText('+2.000001 millilitres')).toBeVisible();
    await page.getByLabel('Language', {exact:true}).selectOption('es');
    await expect(historial.getByText('+2,000001 mililitros')).toBeVisible();
    await expect(historial.getByText('Ajuste manual')).toBeVisible();

    await expect(oil.getByText('La reposición está desactivada.')).toBeVisible();
    await oil.getByRole('button', {name:'Editar reposición'}).click();
    const minimum = oil.getByRole('textbox', {name:'Stock mínimo'});
    const target = oil.getByRole('textbox', {name:'Stock objetivo'});
    await expect(minimum).toBeFocused();
    await minimum.fill('2,000002');
    await target.fill('1');
    await oil.getByRole('button', {name:'Guardar reposición'}).click();
    await expect(oil.getByRole('alert')).toContainText('El objetivo debe ser igual o superior al mínimo.');
    await target.fill('3,250002');
    let policyKey = '';
    await page.route(inventoryCommands, async route => {
      policyKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      expect((await committed.json()).result).toMatchObject({minimum:'2.000002', target:'3.250002', revision:'1'});
      await route.abort('connectionclosed');
    });
    await oil.getByRole('button', {name:'Guardar reposición'}).click();
    await expect(stock.getByText(/El resultado está sin confirmar/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('en');
    const originalPolicy = page.waitForResponse(
      base + 'api/v1/inventory/requests/inventory.configure-replenishment/' + policyKey,
    );
    await stock.getByRole('button', {name:'Recover original request'}).click();
    expect((await originalPolicy).ok()).toBe(true);
    await expect(stock.getByText('Replenishment settings saved.')).toBeVisible();
    await expect(oil.getByText('Replenish · 1.250001 millilitres')).toBeVisible();
    await expect(oil.getByText('Minimum stock · 2.000002 millilitres')).toBeVisible();
    await expect(oil.getByText('Target stock · 3.250002 millilitres')).toBeVisible();
    await oil.getByRole('button', {name:'Edit replenishment'}).click();
    await oil.getByRole('textbox', {name:'Minimum stock'}).fill('2.000001');
    await oil.getByRole('button', {name:'Save replenishment'}).click();
    await expect(oil.getByText('No replenishment needed.')).toBeVisible();
    await page.getByLabel('Language', {exact:true}).selectOption('es');
    await expect(oil.getByText('No hace falta reponer.')).toBeVisible();

    const shopping = stock.locator('domus-shopping');
    await shopping.getByRole('button', {name:'Mostrar compras'}).click();
    await expect(shopping.getByText('No hay compras registradas.')).toBeVisible();
    await shopping.getByRole('combobox', {name:'Artículo comprado'}).selectOption({label:'Pantry oil'});
    await shopping.getByRole('textbox', {name:'Cantidad comprada'}).fill('6,000001');
    await shopping.getByRole('button', {name:'Registrar compra'}).click();
    await expect(stock.getByText('Compra registrada.', {exact:true})).toBeVisible();
    const bought = shopping.getByRole('listitem').filter({hasText:'Pantry oil'});
    await expect(bought.getByText('6,000001 mililitros', {exact:true}).first()).toBeVisible();
    await bought.getByRole('button', {name:'Mostrar recepciones físicas'}).click();
    const arrivalsES = shopping.getByRole('region', {name:'Recepciones físicas · Pantry oil'});
    await expect(arrivalsES.getByRole('heading')).toBeFocused();
    await arrivalsES.getByRole('textbox', {name:'Cantidad recibida'}).fill('7');
    await arrivalsES.getByRole('button', {name:'Registrar recepción física'}).click();
    await expect(arrivalsES.getByRole('alert')).toContainText('no supere lo que queda por recibir');
    await arrivalsES.getByRole('textbox', {name:'Cantidad recibida'}).fill('4,000001');
    await arrivalsES.getByRole('button', {name:'Registrar recepción física'}).click();
    await expect(stock.getByText('Recepción física registrada.', {exact:true})).toBeVisible();
    await expect(arrivalsES.getByText('Recibido, pendiente de entrada en Despensa.')).toBeVisible();
    await expect(oil.locator('dd')).toHaveText(['2,000001','0','2,000001']);
    await page.getByLabel('Idioma', {exact:true}).selectOption('en');
    const arrivals = shopping.getByRole('region', {name:'Physical receipts · Pantry oil'});
    await expect(arrivals.locator('dd')).toHaveText([
      '6.000001 millilitres','4.000001 millilitres','2 millilitres','4.000001 millilitres',
    ]);
    let postingKey = '';
    let postedMovement = '';
    await page.route(inventoryCommands, async route => {
      postingKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      postedMovement = (await committed.json()).result.movement_id;
      await route.abort('connectionclosed');
    });
    await arrivals.getByRole('button', {name:'Post to Pantry'}).click();
    await expect(stock.getByText(/The result is unconfirmed/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('en');
    const originalPosting = page.waitForResponse(
      base + 'api/v1/inventory/requests/shopping.post-receipt/' + postingKey,
    );
    await stock.getByRole('button', {name:'Recover original request'}).click();
    expect((await originalPosting).ok()).toBe(true);
    await expect(stock.getByText('Receipt posted to Pantry.', {exact:true})).toBeVisible();
    await expect(oil.locator('dd')).toHaveText(['6.000002','0','6.000002']);
    await shopping.getByRole('button', {name:'Show purchases'}).click();
    await bought.getByRole('button', {name:'Show physical receipts'}).click();
    await expect(arrivals.locator('dd')).toHaveText([
      '6.000001 millilitres','4.000001 millilitres','2 millilitres','0 millilitres',
    ]);
    await expect(arrivals.getByText('Posted to Pantry.', {exact:true})).toBeVisible();
    await arrivals.getByText('Receipt details').click();
    await expect(arrivals.getByText(postedMovement, {exact:true})).toBeVisible();

    const catalog = await page.request.get(base + 'api/v1/inventory', {headers:{'X-Domus-Context':contextHeader}});
    expect(catalog.ok()).toBe(true);
    const oilProduct = (await catalog.json()).products.find((product: {name:string}) => product.name === 'Pantry oil');
    await post('definitions', 'shopping-task', {
      title:'Mix the dressing', materials:[{reference_id:oilProduct.reference_id,planned_quantity:'7'}],
    });
    await oil.getByRole('button', {name:'Edit replenishment'}).click();
    await oil.getByRole('textbox', {name:'Minimum stock'}).fill('7');
    await oil.getByRole('textbox', {name:'Target stock'}).fill('10');
    await oil.getByRole('button', {name:'Save replenishment'}).click();
    await expect(oil.getByText('Replenish · 3.999998 millilitres')).toBeVisible();
    const shared = shopping.locator('domus-shopping-list');
    await shared.getByRole('button', {name:'Show shared shopping list'}).click();
    const listedOil = shared.getByRole('listitem').filter({has:page.getByText('Pantry oil',{exact:true})});
    await expect(listedOil.locator('dd')).toHaveText([
      '2.999996 millilitres', '1.999998 millilitres', '0.999998 millilitres', '0 millilitres',
    ]);
    await listedOil.getByRole('button', {name:'Show shopping sources'}).click();
    const sources = shared.getByRole('region', {name:'Show shopping sources · Pantry oil'});
    await expect(sources.getByRole('heading')).toBeFocused();
    const taskSource = sources.getByRole('listitem').filter({hasText:'Tasks · Mix the dressing'});
    await expect(taskSource.locator('dd')).toHaveText([
      '7 millilitres', '0 millilitres', '6.000002 millilitres', '0 millilitres', '0.999998 millilitres',
    ]);
    await page.getByLabel('Language', {exact:true}).selectOption('es');
    await expect(shared.getByText('Tareas · Mix the dressing', {exact:true})).toBeVisible();
    await expect(listedOil.getByText('2,999996 mililitros', {exact:true})).toBeVisible();
    await shared.getByRole('combobox', {name:'Artículo para añadir como extra'}).selectOption({label:'Pantry oil'});
    await shared.getByRole('textbox', {name:'Cantidad del extra'}).fill('2,000002');
    let extraKey = '';
    await page.route(inventoryCommands, async route => {
      extraKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      await route.abort('connectionclosed');
    });
    await shared.getByRole('button', {name:'Añadir extra manual'}).click();
    await expect(stock.getByText(/El resultado está sin confirmar/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('es');
    const originalExtra = page.waitForResponse(base + 'api/v1/inventory/requests/shopping.add-extra/' + extraKey);
    await stock.getByRole('button', {name:'Recuperar la solicitud original'}).click();
    expect((await originalExtra).ok()).toBe(true);
    await expect(stock.getByText('Extra manual añadido.', {exact:true})).toBeVisible();
    await shared.getByRole('button', {name:'Mostrar lista compartida de compras'}).click();
    await expect(listedOil.getByText('4,999998 mililitros', {exact:true})).toBeVisible();
    await listedOil.getByRole('button', {name:'Mostrar orígenes de compra'}).click();
    const manual = shared.getByRole('listitem').filter({hasText:'Extras manuales · Pantry oil'});
    await manual.getByRole('button', {name:'Retirar extra manual'}).click();
    await expect(stock.getByText('Extra manual retirado.', {exact:true})).toBeVisible();
    await expect(listedOil.getByText('2,999996 mililitros', {exact:true})).toBeVisible();

    const sessionCsrf = await page.request.get(base + 'api/v1/auth/csrf');
    expect(sessionCsrf.ok()).toBe(true);
    const sessionToken = (await sessionCsrf.json()).csrf_token;
    const inventoryWrite = async (key:string, data:object) => {
      const options = {data,headers:{
        Origin:origin, 'X-Domus-Context':contextHeader, 'X-CSRF-Token':sessionToken, 'Idempotency-Key':key,
      }};
      let response = await page.request.post(inventoryCommands, options);
      if (response.status() === 503) {
        expect((await response.json()).code).toBe('storage_busy');
        expect(response.headers()['retry-after']).toBe('1');
        expect((await request.post(origin + '/__fixture__/writer', {data:{action:'release'}})).ok()).toBe(true);
        await new Promise<void>(resolve => setTimeout(resolve, 1000));
        response = await page.request.post(inventoryCommands, options);
      }
      expect(response.ok(), await response.text()).toBe(true);
      return (await response.json()).result;
    };
    expect((await request.post(origin + '/__fixture__/writer', {data:{action:'acquire'}})).ok()).toBe(true);
    const flourRequest = {action:'inventory.register-product',name:'Session flour',base_unit:'gram'};
    const flour = await inventoryWrite('session-flour', flourRequest);
    expect(await inventoryWrite('session-flour', flourRequest)).toEqual(flour);
    await inventoryWrite('session-flour-policy', {action:'inventory.configure-replenishment',product_id:flour.product_id,
      minimum:'3',target:'3',expected_revision:'0'});
    await inventoryWrite('session-lemons', {action:'shopping.add-extra',product_id:null,name:'Session lemons',quantity:'2'});
    const rice = await inventoryWrite('session-rice', {action:'inventory.register-product',name:'Session rice',base_unit:'gram'});
    await inventoryWrite('session-rice-policy', {action:'inventory.configure-replenishment',product_id:rice.product_id,
      minimum:'2',target:'2',expected_revision:'0'});
    await stock.getByRole('button', {name:'Actualizar inventario'}).click();
    for (const name of ['Session flour','Session lemons','Session rice']) {
      const item = shared.getByRole('listitem').filter({has:page.getByText(name,{exact:true})});
      await item.getByRole('button', {name:'Añadir a la sesión de compra'}).click();
    }
    const draftSession = shared.getByRole('form', {name:'Revisar sesión de compra'});
    await draftSession.getByRole('textbox', {name:'Session flour · gramos'}).fill('2,000001');
    const lemonsQuantity = draftSession.getByRole('textbox', {name:'Session lemons · unidades'});
    await lemonsQuantity.fill('0,5');
    await draftSession.getByRole('textbox', {name:'Session rice · gramos'}).fill('2');
    const store = 'Mercado del Río';
    const spanishStore = draftSession.getByRole('textbox', {name:'Tienda (opcional)'});
    const spanishSave = draftSession.getByRole('button', {name:'Registrar sesión de compra'});
    await page.setViewportSize({width:320,height:720});
    await spanishStore.fill('   ');
    await spanishSave.tap();
    await expect(spanishStore).toHaveValue('   ');
    await expect(spanishStore).toBeFocused();
    await expect(spanishStore).toHaveAttribute('aria-invalid','true');
    await spanishStore.fill(store);
    await spanishSave.tap();
    await expect(lemonsQuantity).toHaveAttribute('aria-invalid','true');
    await expect(spanishStore).toHaveValue(store);
    await lemonsQuantity.fill('1');
    await page.setViewportSize({width:1120,height:900});
    await page.getByRole('combobox',{name:'Idioma'}).selectOption('en');
    const englishDraft = shared.getByRole('form',{name:'Review purchase session'});
    await expect(englishDraft.getByRole('textbox',{name:'Store (optional)'})).toHaveValue(store);
    let sessionKey = '';
    let sessionId = '';
    await page.route(inventoryCommands, async route => {
      sessionKey = route.request().headers()['idempotency-key'];
      const committed = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(committed.status()).toBe(200);
      const {result} = await committed.json();
      sessionId = result.session_id;
      expect(result.purchase_ids).toHaveLength(3);
      expect(result.store_name).toBe(store);
      await route.abort('connectionclosed');
    });
    await englishDraft.getByRole('button',{name:'Record purchase session'}).press('Enter');
    await expect(stock.getByText(/The result is unconfirmed/u)).toBeVisible();
    await page.unroute(inventoryCommands);
    await reopenInventory('en');
    const originalSession = base + 'api/v1/inventory/requests/shopping.record-session/' + sessionKey;
    const recoveredSessionIds: string[] = [];
    await page.route(originalSession, async route => {
      expect(route.request().method()).toBe('GET');
      const response = await route.fetch({maxRetries:0,maxRedirects:0});
      expect(response.status()).toBe(200);
      const body = await response.body();
      recoveredSessionIds.push(JSON.parse(body.toString('utf8')).result.session_id);
      await route.fulfill({response,body});
    });
    await stock.getByRole('button', {name:'Recover original request'}).click();
    await expect(stock.getByText('Purchase session recorded.', {exact:true})).toBeVisible();
    expect(recoveredSessionIds).toEqual([sessionId]);
    await page.unroute(originalSession);
    await shopping.getByRole('button', {name:'Show recorded session'}).click();
    const session = shopping.getByRole('region', {name:/^Session items · /u});
    await expect(session.getByRole('heading')).toBeFocused();
    await expect(session.getByText('Store · '+store,{exact:true})).toBeVisible();
    await page.setViewportSize({width:320,height:720});
    const flourItem = session.getByRole('listitem').filter({hasText:'Session flour'});
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','0 grams','2.000001 grams','0 grams']);
    await expect(session.getByRole('listitem').filter({hasText:'Session lemons'}).locator('dd'))
      .toHaveText(['1 piece','0 pieces','1 piece','0 pieces']);
    await flourItem.getByRole('button', {name:'Show physical receipts'}).click();
    const flourReceipts = shopping.getByRole('region', {name:'Physical receipts · Session flour'});
    await flourReceipts.getByRole('textbox', {name:'Quantity received'}).fill('1.5');
    await flourReceipts.getByRole('button', {name:'Record physical receipt'}).click();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','1.5 grams','0.500001 grams','1.5 grams']);
    const mistaken = flourReceipts.getByRole('listitem').filter({has:page.getByText('1.5 grams',{exact:true})});
    await mistaken.getByText('Void receipt',{exact:true}).click();
    const confirmation = mistaken.locator('.receipt-void-form');
    await expect(confirmation).toContainText('Quantity to void');
    await expect(confirmation).toContainText('1.5 grams');
    await confirmation.getByRole('textbox', {name:'Reason'}).fill('Counted a bag twice');
    await confirmation.getByRole('button', {name:'Confirm receipt void'}).click();
    await expect(stock.getByText('Physical receipt voided.',{exact:true})).toBeVisible();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','0 grams','2.000001 grams','0 grams']);
    await expect(mistaken.getByText('Counted a bag twice',{exact:true})).toBeVisible();
    await expect(mistaken.getByRole('button', {name:'Post to Pantry'})).toHaveCount(0);
    await flourReceipts.getByRole('textbox', {name:'Quantity received'}).fill('1.500001');
    await flourReceipts.getByRole('button', {name:'Record physical receipt'}).click();
    const postedMistake = flourReceipts.getByRole('listitem').filter({has:page.getByText('1.500001 grams',{exact:true})});
    await postedMistake.getByRole('button', {name:'Post to Pantry'}).click();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','1.500001 grams','0.5 grams','0 grams']);
    const flourStock = stock.getByRole('article',{name:'Session flour',exact:true});
    await flourStock.getByRole('button',{name:'Show movement history'}).click();
    const flourHistory = stock.getByRole('region',{name:'Movement history · Session flour'});
    await expect(flourHistory.getByText('Review this receipt in Shopping.',{exact:true})).toBeVisible();
    await expect(flourHistory.getByRole('button',{name:'Reverse this intake'})).toHaveCount(0);
    await flourHistory.getByRole('button',{name:'Close movement history'}).click();

    await postedMistake.getByText('Correct posted receipt',{exact:true}).click();
    const postedCorrection = postedMistake.locator('.posted-receipt-correction-form');
    await expect(postedCorrection).toContainText('1.500001 grams');
    await postedCorrection.getByRole('textbox',{name:'Reason'}).fill('Posted the wrong amount');
    await postedCorrection.getByRole('button',{name:'Confirm posted receipt correction'}).click();
    await expect(stock.getByText('Posted receipt corrected.',{exact:true})).toBeVisible();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','0 grams','2.000001 grams','0 grams']);
    await expect(postedMistake.getByText('Posted the wrong amount',{exact:true})).toBeVisible();
    await flourStock.getByRole('button',{name:'Show movement history'}).click();
    await expect(flourHistory.getByText('-1.500001 grams',{exact:true})).toBeVisible();
    await expect(flourHistory.getByText('+1.500001 grams',{exact:true})).toBeVisible();
    await flourHistory.getByRole('button',{name:'Close movement history'}).click();

    await flourReceipts.getByRole('textbox', {name:'Quantity received'}).fill('1.25');
    await flourReceipts.getByRole('button', {name:'Record physical receipt'}).click();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','1.25 grams','0.750001 grams','1.25 grams']);
    await flourReceipts.getByText('Cancel outstanding balance',{exact:true}).click();
    await expect(flourReceipts.locator('#cancel-form')).toContainText('0.750001 grams');
    await flourReceipts.getByRole('textbox', {name:'Reason'}).fill('Supplier cancelled the rest');
    await flourReceipts.getByRole('button', {name:'Confirm cancellation'}).click();
    await expect(stock.getByText('Outstanding balance cancelled.',{exact:true})).toBeVisible();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','1.25 grams','0 grams','1.25 grams','0.750001 grams']);
    await expect(flourReceipts.getByText('Supplier cancelled the rest',{exact:true})).toBeVisible();
    await expect(flourReceipts.getByRole('button', {name:'Record physical receipt'})).toHaveCount(0);
    await flourReceipts.getByRole('button', {name:'Post to Pantry'}).click();
    await expect(flourItem.locator('dd')).toHaveText(['2.000001 grams','1.25 grams','0 grams','0 grams','0.750001 grams']);
    await shared.getByRole('button', {name:'Show shared shopping list'}).click();
    const listedFlour = shared.getByRole('listitem').filter({has:page.getByText('Session flour',{exact:true})});
    await expect(listedFlour.locator('dd').first()).toHaveText('1.75 grams');
    const riceItem = session.getByRole('listitem').filter({hasText:'Session rice'});
    await riceItem.getByRole('button',{name:'Show physical receipts'}).click();
    const riceReceipts = shopping.getByRole('region',{name:'Physical receipts · Session rice'});
    await riceReceipts.getByRole('textbox',{name:'Quantity received'}).fill('2');
    await riceReceipts.getByRole('button',{name:'Record physical receipt'}).click();
    await riceReceipts.getByRole('button',{name:'Post to Pantry'}).click();
    await expect(riceItem.locator('dd')).toHaveText(['2 grams','2 grams','0 grams','0 grams']);
    await riceReceipts.getByText('Record physical return',{exact:true}).click();
    const returnForm = riceReceipts.locator('.receipt-return-form');
    await expect(returnForm).toContainText('2 grams');
    await returnForm.getByRole('textbox',{name:'Reason'}).fill('Sent the rice back');
    await returnForm.getByRole('button',{name:'Confirm physical return'}).click();
    await expect(stock.getByText('Physical return recorded.',{exact:true})).toBeVisible();
    await expect(riceItem.locator('dd')).toHaveText(['2 grams','2 grams','0 grams','0 grams']);
    await expect(riceReceipts.getByText('Returned from Pantry.',{exact:true})).toBeVisible();
    await expect(riceReceipts.locator('.receipt-return-form')).toHaveCount(0);
    const listedRice = shared.getByRole('listitem').filter({has:page.getByText('Session rice',{exact:true})});
    await expect(listedRice.locator('dd').first()).toHaveText('2 grams');
    const riceStock = stock.getByRole('article',{name:'Session rice',exact:true});
    await riceStock.getByRole('button',{name:'Show movement history'}).click();
    const riceHistory = stock.getByRole('region',{name:'Movement history · Session rice'});
    await expect(riceHistory.getByText('-2 grams',{exact:true})).toBeVisible();
    await expect(riceHistory.getByText('Sent the rice back',{exact:true})).toBeVisible();
    await expect(riceHistory.getByText(/Shopping return/u)).toBeVisible();
    await riceHistory.getByRole('button',{name:'Close movement history'}).click();
    await page.getByLabel('Language',{exact:true}).selectOption('es');
    const sessionHistory = shopping.getByRole('region', {name:'Sesiones de compra',exact:true});
    await sessionHistory.getByRole('button', {name:'Mostrar sesiones de compra'}).click();
    await expect(sessionHistory.getByRole('listitem').getByText('Tienda · '+store,{exact:true})).toBeVisible();
    await sessionHistory.getByRole('button', {name:'Mostrar artículos de la sesión'}).click();
    const sessionEs = shopping.getByRole('region', {name:/^Artículos de la sesión · /u});
    const savedStore = sessionEs.getByText('Tienda · '+store,{exact:true});
    await expect(savedStore).toBeVisible();
    await expect(sessionEs.getByRole('listitem').filter({hasText:'Session lemons'}).locator('dd'))
      .toHaveText(['1 unidad','0 unidades','1 unidad','0 unidades']);
    await savedStore.screenshot({path:info.outputPath('purchase-session-store-es-narrow.png')});
    const flourEs = sessionEs.getByRole('listitem').filter({hasText:'Session flour'});
    await expect(flourEs.getByText('0,750001 gramos',{exact:true})).toBeVisible();
    await flourEs.getByRole('button', {name:'Mostrar recepciones físicas'}).click();
    const receiptsEs = shopping.getByRole('region', {name:'Recepciones físicas · Session flour'});
    await expect(receiptsEs.getByText('Cancelación del saldo',{exact:true})).toBeVisible();
    await expect(receiptsEs.getByText('Supplier cancelled the rest',{exact:true})).toBeVisible();
    await expect(receiptsEs.getByText('Anulada antes de contabilizar en Despensa.',{exact:true})).toBeVisible();
    await expect(receiptsEs.getByText('Counted a bag twice',{exact:true})).toBeVisible();
    await expect(receiptsEs.getByText('Corregida tras contabilizar en Despensa.',{exact:true})).toBeVisible();
    await expect(receiptsEs.getByText('Posted the wrong amount',{exact:true})).toBeVisible();
    await flourStock.getByRole('button',{name:'Mostrar historial de movimientos'}).click();
    const flourHistoryEs = stock.getByRole('region',{name:'Historial de movimientos · Session flour'});
    await expect(flourHistoryEs.getByText('-1,500001 gramos',{exact:true})).toBeVisible();
    await flourHistoryEs.getByRole('button',{name:'Cerrar historial de movimientos'}).click();
    await sessionEs.getByRole('listitem').filter({hasText:'Session rice'}).getByRole('button',{name:'Mostrar recepciones físicas'}).click();
    const riceReceiptsEs = shopping.getByRole('region',{name:'Recepciones físicas · Session rice'});
    await expect(riceReceiptsEs.getByText('Devuelto desde Despensa.',{exact:true})).toBeVisible();
    await expect(riceReceiptsEs.getByText('Sent the rice back',{exact:true})).toBeVisible();
    await riceStock.getByRole('button',{name:'Mostrar historial de movimientos'}).click();
    const riceHistoryEs = stock.getByRole('region',{name:'Historial de movimientos · Session rice'});
    await expect(riceHistoryEs.getByText('-2 gramos',{exact:true})).toBeVisible();
    await expect(riceHistoryEs.getByText(/Devolución de compra/u)).toBeVisible();
    await riceHistoryEs.getByRole('button',{name:'Cerrar historial de movimientos'}).click();

    await page.setViewportSize({width: 1120, height: 900});
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await stock.getByRole('textbox',{name:'Location name'}).fill('Dry shelf');
    await stock.getByRole('button',{name:'Add location'}).press('Enter');
    await expect(stock.getByText('Storage location added.',{exact:true})).toBeVisible();
    const moveFlour = flourStock.getByRole('button',{name:'Move stock'});
    await expect(moveFlour).toBeEnabled();
    await expect(stock.getByRole('textbox',{name:'Location name'})).toHaveValue('');
    await expect(stock.getByRole('textbox',{name:'Location name'})).not.toHaveAttribute('aria-invalid','true');
    await moveFlour.press('Enter');
    const locationDetail = stock.getByRole('region',{name:'Movement history · Session flour'});
    await expect(locationDetail).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(locationDetail.getByRole('combobox',{name:'From location'})).toBeFocused();
    const destination = locationDetail.getByRole('combobox',{name:'To location'});
    await destination.press('End');
    await destination.press('Enter');
    await locationDetail.getByRole('textbox',{name:'Quantity to move'}).fill('2');
    await locationDetail.getByRole('button',{name:'Review transfer'}).press('Enter');
    await expect(locationDetail.getByRole('alert')).toContainText('available stock');
    const amount = locationDetail.getByRole('textbox',{name:'Quantity to move'});
    await expect(amount).toHaveValue('2');
    await amount.fill('0.25');
    await locationDetail.getByRole('button',{name:'Review transfer'}).press('Enter');
    await expect(locationDetail.getByRole('status')).toContainText('Pantry → Dry shelf');
    await locationDetail.getByRole('button',{name:'Confirm transfer'}).press('Enter');
    await expect(locationDetail).toBeFocused();
    await expect(locationDetail.getByText('Pantry → Dry shelf',{exact:true})).toHaveCount(2);
    const total = locationDetail.locator('.location-stock').filter({hasText:'Household total'});
    await expect(total.locator('dd')).toHaveText(['1.25 grams','0 grams','1.25 grams']);
    await expect(locationDetail.locator('.location-stock').filter({hasText:'Dry shelf'}).locator('dd'))
      .toHaveText(['0.25 grams','0 grams','0.25 grams']);
    await expect(locationDetail.locator('.location-stock').filter({hasText:'Pantry'}).locator('dd'))
      .toHaveText(['1 gram','0 grams','1 gram']);
    await locationDetail.screenshot({path:info.outputPath('stock-transfer-en-wide.png')});

    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:320,height:720});
    const locationDetailEs = stock.getByRole('region',{name:'Historial de movimientos · Session flour'});
    await expect(locationDetailEs.locator('.location-stock').filter({hasText:'Despensa'}).locator('dd'))
      .toHaveText(['1 gramo','0 gramos','1 gramo']);
    await locationDetailEs.getByRole('button',{name:'Trasladar stock'}).tap();
    await locationDetailEs.getByRole('combobox',{name:'Ubicación de origen'}).tap();
    await locationDetailEs.getByRole('option',{name:'Dry shelf',exact:true}).tap();
    await locationDetailEs.getByRole('combobox',{name:'Ubicación de destino'}).tap();
    await locationDetailEs.getByRole('option',{name:'Despensa',exact:true}).tap();
    await locationDetailEs.getByRole('textbox',{name:'Cantidad que se trasladará'}).fill('0,25');
    await locationDetailEs.getByRole('button',{name:'Revisar traslado'}).tap();
    await expect(locationDetailEs.getByRole('status')).toContainText('Dry shelf → Despensa');
    await locationDetailEs.getByRole('button',{name:'Confirmar traslado'}).tap();
    await expect(locationDetailEs.getByText('Dry shelf → Despensa',{exact:true})).toHaveCount(2);
    await expect(locationDetailEs.locator('.location-stock').filter({hasText:'Dry shelf'}).locator('dd'))
      .toHaveText(['0 gramos','0 gramos','0 gramos']);
    await locationDetailEs.screenshot({path:info.outputPath('stock-transfer-es-narrow.png')});
    await locationDetailEs.getByRole('button',{name:'Cerrar historial de movimientos'}).tap();

    await tabs.evaluate(element => {element.style.width = '125px';});
    const end = tabs.getByRole('button', {name: 'Desplazar al final', exact: true});
    await expect(end).toBeVisible();
    await end.click();
    const bar = tabs.getByRole('navigation');
    await expect.poll(() => bar.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
    await expect(tabs.getByRole('button', {name: 'Desplazar al inicio', exact: true})).toBeVisible();
    await hogar.focus();
    await page.keyboard.press('Enter');
    await expect(hogar).toHaveAttribute('aria-current', 'page');
    await expect(page).toHaveURL(base + '#household');

    await tabs.evaluate(element => {element.style.removeProperty('width');});
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    const assigned = await post('definitions', 'overview-assigned', {title:'Check the filters'});
    await post('occurrences/' + assigned.occurrence_id + '/claim', 'overview-claim',
      {expected_revision:assigned.revision});
    await post('definitions', 'overview-unclaimed', {title:'Sort the recycling'});
    const lateDefinition = await post('definitions', 'overview-late-definition', {title:'Check window latches'});
    const todayDefinition = await post('definitions', 'overview-today-definition', {title:'Read the water meter'});
    const day = 86_400_000;
    const nextMidnight = (now:number) => Math.floor(now / day + 1) * day;
    const rollover = nextMidnight(Date.now());
    if (rollover - Date.now() < 20_000)
      await expect.poll(() => Date.now(),{timeout:25_000}).toBeGreaterThanOrEqual(rollover);
    const observed = Date.now();
    const overdueWork = await post('definitions/' + lateDefinition.definition_id + '/occurrences','overview-overdue', {
      due_at:observed - 60_000, assignee_ids:[member],
    });
    const dueWork = await post('definitions/' + todayDefinition.definition_id + '/occurrences','overview-today', {
      due_at:nextMidnight(observed) - 1,
    });
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.route(base + 'api/v1/tasks/overview', route => route.abort('failed'), {times:1});
    await overview.click();
    await expect(overviewRegion.getByText('The task summary could not be loaded.')).toBeVisible();
    await expect(overviewRegion.getByRole('heading',{name:/Assigned to me ·/u})).toHaveCount(0);
    await overviewRegion.getByRole('button',{name:'Retry task summary'}).press('Enter');
    const taskSummary = overviewRegion.getByRole('region',{name:'Task summary',exact:true});
    const assignedItem = taskSummary.getByRole('button',{name:'Check the filters · Assigned',exact:true});
    await expect(assignedItem).toBeVisible();
    await expect(taskSummary.getByRole('article',{name:/^Assigned to me ·/u}))
      .toHaveCSS('background-color','rgb(255, 255, 255)');
    await expect(taskSummary.getByRole('heading',{name:'Overdue · 1',exact:true})).toBeVisible();
    await expect(taskSummary.getByRole('heading',{name:'Due today · 1',exact:true})).toBeVisible();
    const overdueItem = taskSummary.getByRole('button',{name:/^Check window latches · .+ · Assigned$/u});
    await expect(overdueItem).toBeVisible();
    await expect(taskSummary.getByRole('button',{name:/^Read the water meter · .+ · Available$/u})).toBeVisible();
    await taskSummary.screenshot({path:info.outputPath('task-overview-en-wide.png')});
    const overdueDetail = page.waitForResponse(base + 'api/v1/tasks/occurrences/' + overdueWork.occurrence_id);
    await overdueItem.press('Enter');
    expect((await overdueDetail).ok()).toBe(true);
    await expect(tasksRegion).toBeFocused();
    await overview.click();
    await expect(assignedItem).toBeVisible();
    await assignedItem.press('Enter');
    await expect(page).toHaveURL(base + '#tasks');
    await expect(tasksRegion).toBeFocused();
    await expect(tasksRegion.getByRole('heading',{name:'Check the filters',exact:true})).toBeVisible();

    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    const resumen = overviewRegion.getByRole('region',{name:'Resumen de tareas',exact:true});
    const unclaimedItem = resumen.getByRole('button',{name:'Sort the recycling · Disponible',exact:true});
    await expect(unclaimedItem).toBeVisible();
    await expect(resumen.getByRole('article',{name:/^Tareas sin asignar ·/u}))
      .toHaveCSS('background-color','rgb(24, 36, 47)');
    await expect(resumen.getByRole('heading',{name:'Vencidas · 1',exact:true})).toBeVisible();
    await expect(resumen.getByRole('heading',{name:'Para hoy · 1',exact:true})).toBeVisible();
    const dueItem = resumen.getByRole('button',{name:/^Read the water meter · .+ · Disponible$/u});
    await resumen.screenshot({path:info.outputPath('task-overview-es-narrow.png')});
    const dueDetail = page.waitForResponse(base + 'api/v1/tasks/occurrences/' + dueWork.occurrence_id);
    await dueItem.tap();
    expect((await dueDetail).ok()).toBe(true);
    await expect(tasksRegion.getByRole('heading',{name:'Read the water meter',exact:true})).toBeFocused();

    const scheduled = await request.post(origin + '/__fixture__/calendar-review');
    expect(scheduled.ok()).toBe(true);
    const {title:maintenanceTitle, future:maintenanceId, new_date:maintenanceDay} = await scheduled.json();
    const maintenanceURL = base + 'api/v1/tasks/occurrences/' + maintenanceId;
    const label = (locale: 'en' | 'es', state: string) => {
      const deadline = new Intl.DateTimeFormat(locale,
        {dateStyle:'medium', timeStyle:'short', timeZone:'UTC'}).format(new Date(maintenanceDay + 'T07:00:00Z'));
      return `${maintenanceTitle} · ${deadline} · ${state}`;
    };
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    await overview.press('Enter');
    await expect(page).toHaveURL(base + '#overview');
    const scheduledEN = taskSummary.getByRole('heading',{name:/^Upcoming maintenance · [12]$/u});
    await expect(scheduledEN).toBeVisible();
    const groupEN = taskSummary.getByRole('article',{name:/^Upcoming maintenance ·/u});
    await expect(groupEN).toHaveCSS('background-color','rgb(255, 255, 255)');
    await groupEN.screenshot({path:info.outputPath('upcoming-maintenance-en-wide.png')});
    const keyboardDetail = page.waitForResponse(maintenanceURL);
    await taskSummary.getByRole('button',{name:label('en','Available'),exact:true}).press('Enter');
    expect((await keyboardDetail).ok()).toBe(true);
    await expect(tasksRegion).toBeFocused();
    await expect(tasksRegion.getByRole('heading',{name:maintenanceTitle,exact:true})).toBeVisible();

    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    const groupES = resumen.getByRole('article',{name:/^Próximos mantenimientos ·/u});
    await expect(groupES).toHaveCSS('background-color','rgb(24, 36, 47)');
    await groupES.screenshot({path:info.outputPath('upcoming-maintenance-es-narrow.png')});
    const touchDetail = page.waitForResponse(maintenanceURL);
    await resumen.getByRole('button',{name:label('es','Disponible'),exact:true}).tap();
    expect((await touchDetail).ok()).toBe(true);
    await expect(tasksRegion).toBeFocused();
    await expect(tasksRegion.getByRole('heading',{name:maintenanceTitle,exact:true})).toBeVisible();

    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await unclaimedItem.tap();
    await expect(page).toHaveURL(base + '#tasks');
    await expect(tasksRegion.getByRole('heading',{name:'Sort the recycling',exact:true})).toBeVisible();

    const previewAPI = base + 'api/v1/automation/preview';
    const definitions = async () => {
      const response = await page.request.get(base + 'api/v1/tasks/definitions', {
        headers: {'X-Domus-Context':contextHeader},
      });
      expect(response.ok(), await response.text()).toBe(true);
      return response.json();
    };
    const beforePreview = await definitions();
    const writeOffset = writes.length;
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    await page.route(base + 'api/v1/inventory?limit=25', route => route.abort('failed'), {times:1});
    await household.press('Enter');
    const rule = page.locator('domus-automation-preview');
    const title = rule.getByRole('textbox',{name:'Proposed task title'});
    const preview = rule.getByRole('button',{name:'Preview rule',exact:true});
    const catalogWarning = rule.getByText('Could not load products. You can preview without a stock condition.');
    const stockCondition = rule.getByRole('combobox',{name:'Stock below minimum (optional)',exact:true});
    await expect(catalogWarning).toBeVisible();
    await expect(stockCondition).toHaveCount(0);
    await preview.press('Enter');
    await expect(title).toBeFocused();
    await expect(rule.getByText('Enter a task title of 1 to 160 characters.')).toBeVisible();
    const longTitle = 'a'.repeat(161);
    await title.fill(longTitle);
    await preview.press('Enter');
    await expect(rule.getByText('Enter a task title of 1 to 160 characters.')).toBeVisible();
    await expect(title).toBeFocused();
    await expect(title).toHaveValue(longTitle);
    expect(writes).toHaveLength(writeOffset);
    const unicodeTitle = '🧹'.repeat(160);
    await title.fill('');
    await title.focus();
    await page.keyboard.insertText(unicodeTitle);
    await expect(title).toHaveValue(unicodeTitle);
    await preview.press('Enter');
    const unicodeProposal = rule.getByText(unicodeTitle,{exact:true});
    await expect(unicodeProposal).toBeVisible();
    await expect(catalogWarning).toBeVisible();
    await rule.getByRole('button',{name:'Try again',exact:true}).press('Enter');
    await expect(preview).toBeEnabled();
    await expect(title).toHaveValue(unicodeTitle);
    await expect(stockCondition).toBeEnabled();
    await expect(catalogWarning).toHaveCount(0);
    await expect(unicodeProposal).toHaveCount(0);
    await title.fill('Check the tea supplies');
    await page.route(previewAPI, route => route.abort('failed'), {times:1});
    await preview.press('Enter');
    await expect(rule.getByText(/Could not preview the rule/u)).toBeVisible();
    await expect(title).toHaveValue('Check the tea supplies');
    await preview.press('Enter');
    await expect(rule.getByRole('status')).toContainText('Would create this task');
    await expect(rule.getByRole('status')).toContainText('Check the tea supplies');
    await expect(rule.getByRole('article',{name:'Automation preview'})).toHaveCSS('background-color','rgb(255, 255, 255)');
    await expect(preview).toHaveCSS('color','rgb(255, 255, 255)');
    await rule.screenshot({path:info.outputPath('automation-preview-en-wide.png')});

    await inventory.click();
    const previewProduct = await inventoryWrite('preview-product', {
      action:'inventory.register-product', name:'Tea filters for preview', base_unit:'piece',
    });
    await inventoryWrite('preview-product-minimum', {action:'inventory.configure-replenishment',
      product_id:previewProduct.product_id, minimum:'2', target:'4', expected_revision:'0'});
    await household.press('Enter');
    await expect(title).toHaveValue('Check the tea supplies');
    await expect(rule.getByRole('status')).toHaveCount(0);
    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await rule.getByRole('combobox',{name:'Existencias por debajo del mínimo (opcional)'}).tap();
    await rule.getByRole('option',{name:'Tea filters for preview',exact:true}).tap();
    const previsualizar = rule.getByRole('button',{name:'Previsualizar regla',exact:true});
    await previsualizar.tap();
    await expect(rule.getByRole('status')).toContainText('Se crearía esta tarea');
    await expect(rule.getByRole('status')).toContainText('Tea filters for preview');
    await expect(rule.getByRole('status')).toContainText('Las existencias disponibles están por debajo del mínimo.');
    await inventoryWrite('preview-stock-intake', {action:'inventory.intake', product_id:previewProduct.product_id, quantity:'2'});
    await previsualizar.tap();
    await expect(rule.getByRole('status')).toContainText('No se crearía ninguna tarea');
    await expect(rule.getByRole('status')).toContainText('No se cumple la condición de existencias.');
    await expect(rule.getByRole('article',{name:'Vista previa de automatización'}))
      .toHaveCSS('background-color','rgb(24, 36, 47)');
    await expect(previsualizar).toHaveCSS('color','rgb(24, 36, 47)');
    await rule.screenshot({path:info.outputPath('automation-preview-es-narrow.png')});
    expect(writes.slice(writeOffset)).toEqual(Array(5).fill('POST ' + previewAPI));
    expect(await definitions()).toEqual(beforePreview);

    const drafts = page.locator('domus-automation-drafts');
    const draftsAPI = base + 'api/v1/automation/drafts';
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    await expect(drafts.getByText('Enter a task title above and save your first draft.')).toBeVisible();
    const saving = page.waitForResponse(response => response.url() === draftsAPI && response.request().method() === 'POST');
    await drafts.getByRole('button',{name:'Save draft',exact:true}).press('Enter');
    const firstDraftSave = await saving;
    expect(firstDraftSave.status()).toBe(200);
    const openDraft = drafts.getByRole('button',{name:'Open Check the tea supplies',exact:true});
    await expect(openDraft).toBeEnabled();
    const firstDraftKey = firstDraftSave.request().headers()['idempotency-key'];
    const firstDraftReceipt = await page.request.get(draftsAPI + '/requests/' + firstDraftKey, {
      headers: {'X-Domus-Context':contextHeader},
    });
    expect(firstDraftReceipt.ok(), await firstDraftReceipt.text()).toBe(true);
    const {result:savedRule} = await firstDraftReceipt.json();
    expect(savedRule).toMatchObject({revision:'1',state:'draft',enabled:false});
    await expect(drafts.getByRole('article',{name:'Automation drafts'})).toHaveCSS('background-color','rgb(255, 255, 255)');
    await drafts.screenshot({path:info.outputPath('automation-drafts-en-wide.png')});
    await page.reload();
    await expect(page).toHaveURL(base + '#household');
    await page.getByRole('combobox',{name:/^(Language|Idioma)$/u}).selectOption('en');
    const draftURL = draftsAPI + '/' + savedRule.rule_id;
    const releaseOpen = Promise.withResolvers<void>();
    await page.route(draftURL, async route => {
      await releaseOpen.promise;
      await route.continue();
    }, {times:1});
    await expect(title).toBeEditable();
    await openDraft.press('Enter');
    try {
      await expect(title).toBeDisabled();
      await expect(stockCondition).toBeDisabled();
    } finally {
      releaseOpen.resolve();
    }
    await expect(title).toHaveValue('Check the tea supplies');
    await expect(title).toBeEditable();
    await expect(stockCondition).toContainText('Tea filters for preview');

    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    const spanishTitle = rule.getByRole('textbox',{name:'Título de la tarea propuesta',exact:true});
    const saveRuleEs = drafts.getByRole('button',{name:'Guardar borrador',exact:true});
    await spanishTitle.fill('Preparar las provisiones de té');
    let lostKey = '';
    const loseResponse = async (route: import('@playwright/test').Route) => {
      if (route.request().method() !== 'POST') {await route.continue(); return;}
      lostKey = (await route.request().allHeaders())['idempotency-key'];
      const committed = await route.fetch();
      expect(committed.ok(), await committed.text()).toBe(true);
      await route.abort('failed');
    };
    await page.route(draftsAPI, loseResponse);
    await saveRuleEs.tap();
    const recoverDraft = drafts.getByRole('button',{name:/^(Check original save|Consultar guardado original)$/u});
    await expect(recoverDraft).toBeEnabled();
    expect(lostKey).toMatch(/^req_[a-f0-9]{32}$/u);
    await page.unroute(draftsAPI, loseResponse);
    await page.route(draftsAPI, route => route.abort('failed'), {times:1});
    await page.reload();
    await expect(drafts.getByText(/Automation drafts are unavailable|Los borradores de automatización no están disponibles/u)).toBeVisible();
    await page.getByRole('combobox',{name:/^(Language|Idioma)$/u}).selectOption('es');
    await expect(spanishTitle).toBeDisabled();
    const releaseList = Promise.withResolvers<void>();
    await page.route(draftsAPI, async route => {
      await releaseList.promise;
      await route.continue();
    }, {times:1});
    await drafts.getByRole('button',{name:'Volver a intentar',exact:true}).tap();
    try {
      await expect(drafts.getByText('Cargando borradores de automatización…')).toBeVisible();
      await expect(spanishTitle).toBeDisabled();
    } finally {
      releaseList.resolve();
    }
    await expect(recoverDraft).toBeEnabled();
    await expect(spanishTitle).toBeDisabled();
    await expect(spanishTitle).toHaveValue('Preparar las provisiones de té');
    const receiptLookup = page.waitForResponse(draftsAPI + '/requests/' + lostKey);
    await recoverDraft.tap();
    expect((await receiptLookup).ok()).toBe(true);
    await expect(drafts.getByRole('status').filter({hasText:'Borrador actual'})).toHaveText(/Revisión 2/u);
    await expect(spanishTitle).toBeEditable();

    const draftToken = await page.request.get(base + 'api/v1/auth/csrf', {headers:{'X-Domus-Context':contextHeader}});
    const competing = await page.request.post(draftsAPI, {headers:{
      Origin:origin, 'X-Domus-Context':contextHeader, 'X-CSRF-Token':(await draftToken.json()).csrf_token,
      'Idempotency-Key':'competing-draft-edit',
    }, data:{rule_id:savedRule.rule_id,expected_revision:'2',version:1,trigger:{kind:'manual'},
      condition:null,
      action:{kind:'task.create',title:'Revisar las compras de té'}}});
    expect(competing.ok(), await competing.text()).toBe(true);
    await spanishTitle.fill('Comprar té para el hogar');
    await saveRuleEs.tap();
    await expect(drafts.getByText(/Otro guardado cambió este borrador/u)).toBeVisible();
    await expect(spanishTitle).toHaveValue('Comprar té para el hogar');
    const reviewRevisionEs = drafts.getByRole('button',{name:'Revisar la última revisión',exact:true});
    await page.route(draftURL, route => route.abort('failed'), {times:1});
    await reviewRevisionEs.tap();
    await expect(drafts.getByText(/Los borradores de automatización no están disponibles/u)).toBeVisible();
    await expect(reviewRevisionEs).toBeEnabled();
    await expect(saveRuleEs).toBeDisabled();
    await expect(spanishTitle).toHaveValue('Comprar té para el hogar');
    await reviewRevisionEs.tap();
    await expect(drafts.getByText('Revisar las compras de té · Revisión 3')).toBeVisible();
    await expect(drafts.getByText('Sin condición de existencias',{exact:true})).toBeVisible();
    await drafts.getByRole('button',{name:'Mantener mis cambios sobre la última revisión',exact:true}).tap();
    await expect(spanishTitle).toHaveValue('Comprar té para el hogar');
    await expect(rule.getByRole('combobox',{name:'Existencias por debajo del mínimo (opcional)'}))
      .toContainText('Tea filters for preview');
    await saveRuleEs.tap();
    await expect(drafts.getByRole('status').filter({hasText:'Borrador actual'})).toHaveText(/Revisión 4/u);
    await expect(drafts.getByRole('article',{name:'Borradores de automatización'})).toHaveCSS('background-color','rgb(24, 36, 47)');
    await drafts.screenshot({path:info.outputPath('automation-drafts-es-narrow.png')});
    expect(await definitions()).toEqual(beforePreview);

    const restock = await inventoryWrite('overview-restock-product', {
      action:'inventory.register-product', name:'Filters for the Overview', base_unit:'piece',
    });
    await inventoryWrite('overview-restock-policy', {action:'inventory.configure-replenishment',
      product_id:restock.product_id, minimum:'2', target:'4', expected_revision:'0'});
    await inventoryWrite('overview-restock-one', {action:'inventory.intake', product_id:restock.product_id, quantity:'1'});
    const overviewExtra = await inventoryWrite('overview-shopping-extra', {
      action:'shopping.add-extra', product_id:null, name:'Paper bags for the Overview', quantity:'2',
    });
    await page.getByLabel('Idioma',{exact:true}).selectOption('en');
    await page.setViewportSize({width:1100,height:760});
    await page.emulateMedia({colorScheme:'light'});
    await page.route(base + 'api/v1/inventory/stock-attention', route => route.abort('failed'), {times:1});
    await overview.press('Enter');
    const attention = overviewRegion.locator('domus-stock-attention');
    await expect(attention.getByText('The inventory summary could not be loaded.')).toBeVisible();
    await expect(taskSummary.getByRole('heading',{name:/^Upcoming maintenance ·/u})).toBeVisible();
    await attention.getByRole('button',{name:'Retry inventory summary',exact:true}).press('Enter');
    const restockRow = attention.getByRole('listitem').filter({hasText:'Filters for the Overview'});
    await expect(restockRow).toContainText('Available stock 1 piece');
    await expect(restockRow).toContainText('Minimum stock 2 pieces');
    await expect(attention.getByRole('article')).toHaveCSS('background-color','rgb(255, 255, 255)');
    await attention.screenshot({path:info.outputPath('stock-attention-en-wide.png')});
    const shoppingSummary = overviewRegion.locator('domus-shopping-attention');
    await expect(shoppingSummary.getByRole('heading',{name:/^Items to buy · [1-9]/u})).toBeVisible();
    const shoppingRow = shoppingSummary.getByRole('link',{name:'Filters for the Overview 3 pieces',exact:true});
    await expect(shoppingRow).toBeVisible();
    await shoppingRow.press('Enter');
    const sharedList = stock.locator('domus-shopping-list');
    await expect(sharedList.getByRole('listitem').getByText('Filters for the Overview',{exact:true})).toBeFocused();
    await inventory.press('Enter');
    await expect(page).toHaveURL(base + '#inventory');
    await overview.press('Enter');
    await attention.getByRole('link',{name:'Open Inventory',exact:true}).press('Enter');
    await expect(stock).toBeFocused();

    await page.getByLabel('Language',{exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await expect(restockRow).toContainText('Stock disponible 1 unidad');
    await expect(restockRow).toContainText('Stock mínimo 2 unidades');
    await expect(attention.getByRole('article')).toHaveCSS('background-color','rgb(24, 36, 47)');
    await attention.screenshot({path:info.outputPath('stock-attention-es-narrow.png')});
    await expect(shoppingSummary.getByRole('heading',{name:/^Artículos por comprar · [1-9]/u})).toBeVisible();
    const extraLink = shoppingSummary.getByRole('link',{name:'Paper bags for the Overview 2 unidades',exact:true});
    const oldFragment = await extraLink.getAttribute('href');
    await extraLink.tap();
    await expect(sharedList.getByRole('listitem').getByText('Paper bags for the Overview',{exact:true})).toBeFocused();
    await inventoryWrite('overview-shopping-clear', {
      action:'shopping.clear-extra', extra_id:overviewExtra.extra_id,
    });
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await expect(page).toHaveURL(base + '#overview');
    await expect(shoppingSummary.getByRole('heading',{name:/^Artículos por comprar · [1-9]/u})).toBeVisible();
    await expect(extraLink).toHaveCount(0);
    await page.evaluate(fragment => {location.hash = fragment!;}, oldFragment);
    await expect(sharedList.getByRole('heading',{name:'Lista compartida de compras'})).toBeFocused();
    await expect(sharedList.getByRole('status')).toContainText('Este artículo ya no está pendiente de compra.');
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await attention.getByRole('link',{name:'Abrir Inventario',exact:true}).tap();
    await expect(stock).toBeFocused();
    const restockProduct = stock.getByRole('article',{name:'Filters for the Overview',exact:true});
    await restockProduct.getByRole('button',{name:'Registrar entrada de stock',exact:true}).tap();
    await restockProduct.getByRole('textbox',{name:'Cantidad que se añadirá',exact:true}).fill('1');
    await restockProduct.getByRole('button',{name:'Revisar entrada',exact:true}).tap();
    await expect(restockProduct.getByRole('status')).toContainText('1 unidad.');
    await restockProduct.getByRole('button',{name:'Confirmar entrada',exact:true}).tap();
    await expect(restockProduct.getByText('No hace falta reponer.',{exact:true})).toBeVisible();
    await tabs.getByRole('link',{name:'Inicio',exact:true}).tap();
    await expect(attention.getByRole('heading',{name:/^Productos por debajo del mínimo ·/u})).toBeVisible();
    await expect(restockRow).toHaveCount(0);
  });
}

for (const mode of ['native', 'standalone'] as const) {
  test(`manual automation confirmation and original receipt in ${mode}`, async ({page, context, request}, info) => {
    test.setTimeout(90_000);
    const origin = `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
    const base = origin + (mode === 'native' ? ingress : '') + '/';
    if (process.env.DOMUS_BROWSER_IMAGE) {
      const answer = await request.get(origin + '/__fixture__/image');
      expect(answer.ok()).toBe(true);
      expect(await answer.json()).toEqual({
        source_commit: process.env.DOMUS_TEST_SOURCE_COMMIT, architecture: process.env.DOMUS_TEST_ARCH,
        image_id: expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode,
      });
    }
    expect((await request.post(origin + '/__fixture__/reset')).ok()).toBe(true);
    if (mode === 'native') await context.addCookies([{name:'ingress_session', value:'f'.repeat(128),
      domain:'127.0.0.1', path:'/', httpOnly:true, sameSite:'Strict'}]);
    await page.goto(base + '#household');
    if (mode === 'standalone') {
      await page.getByRole('button',{name:'Sign in with Home Assistant',exact:true}).click();
      await page.getByRole('link',{name:'Continue as fixture user',exact:true}).click();
    }
    await page.getByRole('textbox',{name:'Household name',exact:true}).fill('Manual Rule Fixture');
    await page.getByRole('textbox',{name:'Timezone',exact:true}).fill('UTC');
    const draftsURL = base + 'api/v1/automation/drafts';
    const initialList = page.waitForResponse(response =>
      response.url() === draftsURL && response.request().method() === 'GET');
    await page.getByRole('button',{name:'Create household',exact:true}).press('Enter');
    const tabs = page.locator('vyp-ha-tabs');
    const house = tabs.getByRole('link',{name:'Household',exact:true});
    await house.click();
    const contextHeader = (await (await initialList).request().allHeaders())['x-domus-context'];
    const stockWrite = async (key: string, data: object) => {
      const token = await page.request.get(base + 'api/v1/auth/csrf', {headers:{'X-Domus-Context':contextHeader}});
      const answer = await page.request.post(base + 'api/v1/inventory/commands', {headers:{
        Origin:origin, 'X-Domus-Context':contextHeader, 'X-CSRF-Token':(await token.json()).csrf_token,
        'Idempotency-Key':key,
      }, data});
      expect(answer.ok(), await answer.text()).toBe(true);
      return (await answer.json()).result;
    };
    const {product_id:product} = await stockWrite('new-test-product', {
      action:'inventory.register-product',name:'Fixture filters',base_unit:'piece',
    });
    await stockWrite('new-test-minimum', {action:'inventory.configure-replenishment', product_id:product,
      minimum:'2',target:'4',expected_revision:'0'});
    await stockWrite('initial-test-intake',{action:'inventory.intake',product_id:product,quantity:'2'});
    await tabs.getByRole('link',{name:'Inventory',exact:true}).click();
    await expect(page).toHaveURL(base + '#inventory');
    await house.click();
    await expect(page).toHaveURL(base + '#household');
    const preview = page.locator('domus-automation-preview');
    const drafts = page.locator('domus-automation-drafts');
    const execution = page.locator('domus-automation-execution');
    const draftTitle = 'Inspect the fixture filters';
    await preview.getByRole('textbox',{name:'Proposed task title',exact:true}).fill(draftTitle);
    await preview.getByRole('combobox',{name:'Stock below minimum (optional)',exact:true}).click();
    await preview.getByRole('option',{name:'Fixture filters',exact:true}).click();
    const saved = page.waitForResponse(response => response.url() === draftsURL && response.request().method() === 'POST');
    await drafts.getByRole('button',{name:'Save draft',exact:true}).press('Enter');
    const saving = await saved;
    expect(saving.ok()).toBe(true);
    const draftKey = (await saving.request().allHeaders())['idempotency-key'];
    const draftReceipt = await page.request.get(draftsURL + '/requests/' + draftKey,
      {headers:{'X-Domus-Context':contextHeader}});
    expect(draftReceipt.ok(), await draftReceipt.text()).toBe(true);
    const {result:rule} = await draftReceipt.json();
    const runsURL = draftsURL + '/' + rule.rule_id + '/runs';
    let requestedRuns = 0;
    page.on('request', item => {
      if (item.url() === runsURL && item.method() === 'POST') requestedRuns++;
    });

    const schedule = page.locator('domus-automation-schedule-preview');
    const dailyField = schedule.getByRole('textbox',{name:'Time each day',exact:true});
    const previewURL = base + 'api/v1/automation/schedule-preview?time=07%3A30';
    const scheduleRequests: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/automation/schedule-preview')) scheduleRequests.push(request.method());
    });
    await dailyField.fill('24:00');
    await schedule.getByRole('button',{name:'Preview daily times',exact:true}).press('Enter');
    await expect(schedule.getByText('Enter a time between 00:00 and 23:59.',{exact:true})).toBeVisible();
    await expect(dailyField).toBeFocused();
    expect(scheduleRequests).toEqual([]);
    await dailyField.fill('07:30');
    const previewRead = page.waitForResponse(previewURL);
    await dailyField.press('Enter');
    expect((await previewRead).ok()).toBe(true);
    await expect(schedule.getByRole('listitem')).toHaveCount(5);
    await expect(schedule.locator('time').first()).toHaveAttribute('datetime', /T07:30:00\.000Z$/u);
    await schedule.screenshot({path:info.outputPath('daily-preview-en-wide.png')});

    const history = page.locator('domus-automation-run-history');
    await history.getByRole('button',{name:'Show run history',exact:true}).press('Enter');
    await expect(history.getByText('You have no manual runs for this rule.',{exact:true})).toBeVisible();
    await history.getByRole('button',{name:'Hide run history',exact:true}).press('Enter');
    await expect(history.getByRole('list')).toHaveCount(0);

    await expect(execution.getByText('Disabled',{exact:true})).toBeVisible();
    await execution.getByRole('button',{name:'Enable saved revision',exact:true}).press('Enter');
    const confirmation = execution.getByRole('region',{name:'Confirm automation action',exact:true});
    await expect(confirmation.getByRole('heading')).toBeFocused();
    await expect(confirmation.getByText('Revision 1 · ' + draftTitle,{exact:true})).toBeVisible();
    await confirmation.getByRole('button',{name:'Enable this revision',exact:true}).press('Enter');
    const run = execution.getByRole('button',{name:'Run manually',exact:true});
    await expect(run).toBeEnabled();
    await run.press('Enter');
    await expect(confirmation.getByText('Revision 1 · ' + draftTitle,{exact:true})).toBeVisible();
    expect(requestedRuns).toBe(0);
    await execution.screenshot({path:info.outputPath('manual-confirmation-en-wide.png')});
    await confirmation.getByRole('button',{name:'Run this revision',exact:true}).press('Enter');
    await expect(execution.getByText('The stock condition did not match. No task was created.',{exact:true})).toBeVisible();
    await expect(execution.getByRole('link',{name:'Open created task'})).toHaveCount(0);

    const trigger = drafts.getByRole('combobox',{name:'Trigger',exact:true});
    await trigger.press('Enter');
    await trigger.press('End');
    await trigger.press('Enter');
    await expect(drafts.getByText(/Daily drafts stay inactive/u)).toBeVisible();
    let dailyKey = '';
    await page.route(draftsURL, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      dailyKey = (await route.request().allHeaders())['idempotency-key'];
      expect(route.request().postDataJSON()).toMatchObject({
        version:2,trigger:{kind:'daily',time:'07:30'},rule_id:rule.rule_id,expected_revision:'1',
      });
      const committed = await route.fetch();
      expect(committed.ok(),await committed.text()).toBe(true);
      await route.abort('failed');
    });
    await drafts.getByRole('button',{name:'Save draft',exact:true}).press('Enter');
    const recoverDraft = drafts.getByRole('button',{name:'Check original save',exact:true});
    await expect(recoverDraft).toBeEnabled();
    expect(dailyKey).toMatch(/^req_[a-f0-9]{32}$/u);
    await page.unroute(draftsURL);
    await page.reload();
    await expect(recoverDraft).toBeEnabled();
    await expect(dailyField).toHaveValue('07:30');
    await expect(dailyField).not.toBeEditable();
    const dailyReceipt = page.waitForResponse(draftsURL + '/requests/' + dailyKey);
    await recoverDraft.press('Enter');
    expect((await dailyReceipt).ok()).toBe(true);
    await expect(drafts.getByText('Draft saved.',{exact:true})).toBeVisible();
    await expect(dailyField).toBeEditable();
    await expect(execution.getByText('The latest daily draft remains inactive.',{exact:true})).toBeVisible();
    await expect(execution.getByRole('button',{name:'Enable saved revision',exact:true})).toHaveCount(0);
    await expect(run).toBeEnabled();

    await stockWrite('test-stock-change',{action:'inventory.adjust',product_id:product,quantity:'-1',reason:'Counted one less'});
    await page.getByRole('combobox',{name:'Language',exact:true}).selectOption('es');
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({colorScheme:'dark'});
    await page.route(previewURL, route => route.abort('failed'), {times:1});
    await schedule.getByRole('button',{name:'Previsualizar horario diario',exact:true}).tap();
    await expect(schedule.getByText('El horario diario no está disponible en este momento.',{exact:true})).toBeVisible();
    await expect(schedule.getByRole('textbox',{name:'Hora de cada día',exact:true})).toHaveValue('07:30');
    const nextPreview = page.waitForResponse(previewURL);
    await schedule.getByRole('button',{name:'Volver a intentar',exact:true}).tap();
    expect((await nextPreview).ok()).toBe(true);
    await expect(schedule.getByRole('heading',{name:'Próximas cinco fechas',exact:true})).toBeVisible();
    await expect(schedule.getByRole('listitem')).toHaveCount(5);
    expect(scheduleRequests).toEqual(['GET','GET','GET']);
    await schedule.screenshot({path:info.outputPath('daily-preview-es-narrow.png')});
    let exactKey = '', taskId = '';
    await page.route(runsURL, async route => {
      exactKey = (await route.request().allHeaders())['idempotency-key'];
      const committed = await route.fetch();
      expect(committed.ok(), await committed.text()).toBe(true);
      taskId = (await committed.json()).result.task_occurrence_id;
      await route.abort('failed');
    }, {times:1});
    await execution.getByRole('button',{name:'Ejecutar manualmente',exact:true}).tap();
    await execution.getByRole('button',{name:'Ejecutar esta revisión',exact:true}).tap();
    const recover = execution.getByRole('button',{name:/^(Check original request|Consultar solicitud original)$/u});
    await expect(recover).toBeEnabled();
    expect(exactKey).toMatch(/^req_[a-f0-9]{32}$/u);
    expect(taskId).toMatch(/^domus_/u);
    await page.reload();
    await expect(recover).toBeEnabled();
    await page.getByRole('combobox',{name:/^(Language|Idioma)$/u}).selectOption('es');
    const original = page.waitForResponse(base + 'api/v1/automation/execution/requests/run/' + exactKey);
    await recover.tap();
    expect((await original).ok()).toBe(true);
    await expect(execution.getByText('Tarea creada.',{exact:true})).toBeVisible();
    expect(requestedRuns).toBe(2);
    await execution.screenshot({path:info.outputPath('manual-original-es-narrow.png')});
    const detail = page.waitForResponse(base + 'api/v1/tasks/occurrences/' + taskId);
    await execution.getByRole('link',{name:'Abrir tarea creada',exact:true}).tap();
    expect((await detail).ok()).toBe(true);
    await expect(page).toHaveURL(base + '#tasks');
    await expect(page.locator('domus-tasks').getByRole('heading',{name:draftTitle,exact:true})).toBeVisible();

    await tabs.getByRole('link',{name:'Hogar',exact:true}).tap();
    await drafts.getByRole('button',{name:'Abrir ' + draftTitle,exact:true}).tap();
    await stockWrite('refill-for-later-no-task-runs',{action:'inventory.adjust',product_id:product,
      quantity:'2',reason:'Replenished for history test'});
    const token = await page.request.get(base + 'api/v1/auth/csrf', {headers:{'X-Domus-Context':contextHeader}});
    expect(token.ok()).toBe(true);
    const csrf = (await token.json()).csrf_token;
    const writeHeaders = {Origin:origin, 'X-Domus-Context':contextHeader, 'X-CSRF-Token':csrf};
    const secondDraft = await page.request.post(draftsURL, {data:{
      version:1, trigger:{kind:'manual'}, condition:null,
      action:{kind:'task.create',title:'Inspect the fixture shelf'}, rule_id:null, expected_revision:'0',
    }, headers:{...writeHeaders, 'Idempotency-Key':'separate-history-rule'}});
    expect(secondDraft.ok(), await secondDraft.text()).toBe(true);
    for (let index = 0; index < 25; index++) {
      const newer = await page.request.post(runsURL, {data:{rule_revision:'1',control_revision:'1'},
        headers:{...writeHeaders, 'Idempotency-Key':'additional-history-run-' + index}});
      expect(newer.ok(), await newer.text()).toBe(true);
      expect((await newer.json()).result.condition_matched).toBe(false);
    }

    const disable = execution.getByRole('button',{name:'Deshabilitar futuras ejecuciones',exact:true});
    await disable.tap();
    await execution.getByRole('region',{name:'Confirmar acción de automatización',exact:true})
      .getByRole('button',{name:'Deshabilitar futuras ejecuciones',exact:true}).tap();
    await expect(execution.getByText('Futuras ejecuciones deshabilitadas.',{exact:true})).toBeVisible();
    await expect(execution.getByRole('button',{name:'Ejecutar manualmente',exact:true})).toHaveCount(0);

    await history.getByRole('button',{name:'Mostrar historial',exact:true}).tap();
    await expect(history.getByRole('listitem')).toHaveCount(25);
    await expect(history.getByRole('link',{name:'Abrir tarea creada',exact:true})).toHaveCount(0);
    const olderPage = (url: URL) => url.origin + url.pathname === runsURL && url.searchParams.has('cursor');
    await page.route(olderPage, route => route.abort('failed'), {times:1});
    await history.getByRole('button',{name:'Ejecuciones anteriores',exact:true}).tap();
    await expect(history.getByText('El historial no está disponible en este momento.',{exact:true})).toBeVisible();
    await expect(history.getByRole('listitem')).toHaveCount(25);

    const retry = page.waitForResponse(reply => olderPage(new URL(reply.url())) && reply.request().method() === 'GET');
    await history.getByRole('button',{name:'Volver a intentar',exact:true}).tap();
    expect((await retry).ok()).toBe(true);
    await expect(history.getByRole('listitem')).toHaveCount(2);
    await expect(history.getByText('Tarea creada.',{exact:true})).toBeVisible();
    await expect(history.getByText('No se cumplió la condición de existencias. No se creó ninguna tarea.',{exact:true})).toBeVisible();
    await expect(history.locator('time').first()).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/u);
    await history.screenshot({path:info.outputPath('manual-history-es-narrow.png')});
    const originalTask = page.waitForResponse(base + 'api/v1/tasks/occurrences/' + taskId);
    await history.getByRole('link',{name:'Abrir tarea creada',exact:true}).tap();
    expect((await originalTask).ok()).toBe(true);
    await expect(page.locator('domus-tasks').getByRole('heading',{name:draftTitle,exact:true})).toBeVisible();
    await tabs.getByRole('link',{name:'Hogar',exact:true}).tap();
    await expect(history.getByRole('listitem')).toHaveCount(0);
    await drafts.getByRole('button',{name:'Abrir ' + draftTitle,exact:true}).tap();
    await expect(drafts.getByText(/Los borradores diarios permanecen inactivos/u)).toBeVisible();
    await expect(schedule.getByRole('textbox',{name:'Hora de cada día',exact:true})).toHaveValue('07:30');
    await drafts.screenshot({path:info.outputPath('daily-draft-es-narrow.png')});
    await history.getByRole('button',{name:'Mostrar historial',exact:true}).tap();
    await expect(history.getByRole('listitem')).toHaveCount(25);
    await drafts.getByRole('button',{name:'Abrir Inspect the fixture shelf',exact:true}).tap();
    await expect(history.getByRole('listitem')).toHaveCount(0);
    await history.getByRole('button',{name:'Mostrar historial',exact:true}).tap();
    await expect(history.getByText('No tienes ejecuciones manuales para esta regla.',{exact:true})).toBeVisible();
  });
}
