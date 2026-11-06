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
    await page.reload(); await expect(tasks.getByRole('button', {name: title, exact: true})).toBeVisible();
    await tasks.getByRole('button', {name: title, exact: true}).click();
    await expect(tasks.getByText('No approval required', {exact: true})).toBeVisible();
    const stats = await (await page.request.get(origin(mode) + '/__fixture__/stats')).json(); expect(stats.counts.receipts).toBe(4);
    if (mode === 'native' && !spanish) await page.screenshot({path: 'test-results/tasks-native-completed.png', fullPage: true});
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
    await tasks.getByLabel('Title', {exact: true}).fill('a'.repeat(161));
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
