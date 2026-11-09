import {expect, test} from '@playwright/test';

const ingress = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';

for (const mode of ['native', 'standalone'] as const) {
  test(`shared workspace navigation in ${mode}`, async ({page, context, request}, info) => {
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
    await family.focus();
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
    await familyRegion.getByRole('button', {name: 'Actualizar'}).click();
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
