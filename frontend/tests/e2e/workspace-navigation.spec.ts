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
    await expect(calendarRegion.getByText('Entradas que coinciden 0')).toBeVisible();
    await expect(calendarRegion.locator('.calendar-grid')).toHaveCount(0);
    const unicodeCategory = '🌿'.repeat(64);
    await calendarRegion.getByLabel('Etiqueta de categoría', {exact:true}).fill(unicodeCategory);
    const categoryRead = page.waitForResponse(response => response.url().startsWith(base + 'api/v1/tasks/calendar?')
      && new URL(response.url()).searchParams.get('category') === unicodeCategory);
    await calendarRegion.getByRole('button', {name:'Mostrar calendario',exact:true}).click();
    expect((await categoryRead).ok()).toBe(true);


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
      await route.abort('connectionclosed');
    });
    await choose.selectOption('sunday');
    await expect(recover).toBeEnabled();
    await expect(calendarRegion.getByRole('alert')).toContainText('El cambio está sin confirmar');
    await page.reload();
    const recovered = calendarRegion.getByRole('button', {name:'Check original week-start change'});
    await expect(recovered).toBeEnabled();
    const original = page.waitForResponse(response => response.url() === pref + '/requests/' + originalKey);
    await recovered.click();
    const originalResponse = await original;
    expect(originalResponse.ok()).toBe(true);
    expect(await originalResponse.text()).toContain('"revision":9007199254740994');
    await expect(recovered).toHaveCount(0);
    await expect(calendarRegion.getByLabel('My week starts on')).toHaveValue('sunday');
    expect(writes).toEqual(['POST ' + base + 'api/v1/household', 'PUT ' + pref]);
    await page.getByLabel('Language', {exact: true}).selectOption('es');

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
