import {expect, test} from '@playwright/test';

const ingress = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';

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
    const seeded = await post('definitions', 'family-work', {
      title: 'Water plants', overrides: {point_value_minor: 225},
    });
    const done = await post('occurrences/' + seeded.occurrence_id + '/complete', 'family-completed', {
      expected_revision: seeded.revision, performer_ids: [member], performed_at: Date.now() - 500,
    });
    const ledger = async () => {
      const result = await page.request.get(firstFamily.url(), {headers: {'X-Domus-Context': contextHeader}});
      expect(result.ok(), await result.text()).toBe(true);
      return result.json();
    };
    await expect.poll(async () => (await ledger()).available_minor, {timeout: 15_000}).toBe(225);
    const familia = tabs.getByRole('link', {name: 'Familia', exact: true});
    await familia.click();
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
    await expect.poll(async () => (await ledger()).history.length, {timeout: 15_000}).toBe(2);
    await familyRegion.getByRole('button', {name: 'Actualizar', exact: true}).click();
    await expect(familyRegion.getByText('Reversión −2,25', {exact: true})).toBeVisible();
    await expect(familyRegion.getByText('Premio original', {exact: true})).toBeVisible();
    await familyRegion.screenshot({path: info.outputPath('family-es-reversal.png')});
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await expect(familyRegion.getByText('Reversal −2.25', {exact: true})).toBeVisible();
    await familyRegion.screenshot({path: info.outputPath('family-en-reversal.png')});
    await page.getByLabel('Language', {exact: true}).selectOption('es');

    const settings = familyRegion.locator('domus-allocation-settings');
    await settings.getByRole('combobox', {name: 'Política', exact: true}).selectOption('equal_share');
    await settings.getByRole('combobox', {name: 'Redondeo', exact: true}).selectOption('ceil');
    await settings.getByRole('button', {name: 'Guardar política', exact: true}).click();
    await expect(settings.getByText('Política de puntos guardada.', {exact: true})).toBeVisible();
    await tabs.getByRole('link', {name: 'Tareas', exact: true}).click();
    await tasksRegion.getByRole('button', {name: 'Actualizar tareas', exact: true}).click();
    await tasksRegion.getByRole('button', {name: 'Water plants', exact: true}).click();
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
    await expect.poll(async () => (await ledger()).available_minor, {timeout: 15_000}).toBe(300);
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
    await expect.poll(async () => (await ledger()).reserved_minor).toBe(200);
    const latest = await (await page.request.get(base + 'api/v1/tasks/occurrences/' + seeded.occurrence_id,
      {headers: {'X-Domus-Context': contextHeader}})).json();
    await post('occurrences/' + seeded.occurrence_id + '/reopen', 'family-reward-hold', {
      expected_revision: latest.work.revision, cycle_id: latest.cycle.cycle_id, reason: 'Check the reward funding',
    });
    await expect.poll(async () => (await ledger()).available_minor, {timeout: 15_000}).toBe(-200);
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
    await expect.poll(async () => (await ledger()).available_minor, {timeout: 15_000}).toBe(100);
    await rewards.getByRole('button', {name: 'Refresh rewards'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Approved for delivery'})).toBeVisible();
    expect((await ledger()).spending_count).toBe(0);
    await rewards.getByRole('checkbox', {name: 'I delivered this reward'}).check();
    await rewards.getByRole('button', {name: 'Record delivery'}).click();
    await expect(rewards.locator('li').filter({hasText: 'Spending recorded'})).toBeVisible();
    await expect(familyRegion.getByText('Spent in this period 2.00')).toBeVisible();
    await post('occurrences/' + newCredit.occurrence_id + '/reopen', 'family-reward-negative', {
      expected_revision: earned.revision, cycle_id: earned.cycle.cycle_id, reason: 'Check the original work',
    });
    await expect.poll(async () => (await ledger()).posted_minor, {timeout: 15_000}).toBe(-200);
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
    await page.reload();
    await expect(page).toHaveURL(base + '#inventory');
    await page.getByRole('combobox', {name:/^(Language|Idioma)$/u}).selectOption('es');
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
    await page.reload();
    await expect(page).toHaveURL(base + '#inventory');
    await page.getByRole('combobox', {name:/^(Language|Idioma)$/u}).selectOption('en');
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
  });
}
