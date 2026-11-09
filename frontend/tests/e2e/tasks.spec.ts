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
      await memberTasks.getByRole('button', {name: 'Claim task', exact: true}).click();
      await memberTasks.locator('summary').filter({hasText: 'Saved requests'}).click();
      await memberTasks.getByRole('button', {name: 'Dismiss saved request', exact: true}).click();
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
      const recovered = page.waitForResponse(item => item.request().method() === 'GET' && item.url().endsWith('/' + originalKey));
      await review.getByRole('button', {name: 'Check original schedule request', exact: true}).last().click();
      expect((await recovered).ok()).toBe(true);
      await expect(review.getByRole('heading', {name: 'Schedule change saved', exact: true})).toBeVisible();
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
