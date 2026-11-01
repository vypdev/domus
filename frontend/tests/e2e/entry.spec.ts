import {expect, test} from '@playwright/test';
import type {APIRequestContext, BrowserContext, Page} from '@playwright/test';

const prefix = '/api/hassio_ingress/fixture_domus_supervisor_1234567890';
const journalKey = 'domus.entry.journal.v1';
const modes = ['native', 'standalone'] as const;
type Mode = typeof modes[number];
const origin = (mode: Mode) => `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
const base = (mode: Mode) => origin(mode) + (mode === 'native' ? prefix : '');
const stats = async (request: APIRequestContext, mode: Mode) =>
  (await request.get(origin(mode) + '/__fixture__/stats')).json();
async function open(page: Page, context: BrowserContext, mode: Mode, signIn = true) {
  if (mode === 'native') await context.addCookies([{name: 'ingress_session', value: 'f'.repeat(128),
    domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
  const response = await page.goto(base(mode) + '/');
  expect(response?.status()).toBe(200);
  if (mode === 'standalone' && signIn) {
    await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Fictional Home Assistant'})).toBeVisible();
    await page.getByRole('link', {name: 'Continue as fixture user'}).click();
  }
  if (signIn) await expect(page.getByRole('heading', {name: 'Set up your household', exact: true})).toBeVisible();
  return response!;
}
async function create(page: Page, name = 'Fictional household') {
  await page.getByLabel('Household name', {exact: true}).fill(name);
  await page.getByLabel('Timezone', {exact: true}).fill('Europe/Madrid');
  await page.getByRole('button', {name: 'Create household', exact: true}).click();
}

for (const mode of modes) test.describe(mode, () => {
  test.beforeEach(async ({request}) => {
    expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
  });

  test('opening and refreshing are read-only and every product resource uses its own base', async ({page, context, request}) => {
    const writes: string[] = [], resources: string[] = [], errors: string[] = [];
    page.on('request', item => {
      if (item.url().startsWith(base(mode)) && item.method() === 'POST') writes.push(item.url());
      if (item.url().includes('/assets/') || item.url().includes('/api/v1/')) resources.push(item.url());
    });
    page.on('pageerror', error => errors.push(error.message));
    const response = await open(page, context, mode);
    await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
    await expect(page.getByRole('button', {name: 'Create household', exact: true})).toBeEnabled();
    expect((await stats(request, mode)).counts.households).toBe(0);
    expect(writes).toEqual([]); expect(errors).toEqual([]);
    expect(resources.some(item => item.includes('/assets/'))).toBe(true);
    expect(resources.some(item => item.endsWith('/api/v1/authorization'))).toBe(true);
    expect(resources.every(item => item.startsWith(base(mode) + '/'))).toBe(true);
    expect(response.headers()['content-security-policy']).toContain("script-src 'self'");
    expect(response.headers()['content-security-policy']).not.toMatch(/unsafe-inline|unsafe-eval/);
    const bootstrap = await page.locator('#domus-bootstrap').textContent();
    expect(Object.keys(JSON.parse(bootstrap!)).sort()).toEqual(['application_base', 'deployment', 'style_nonce', 'version']);
    expect(bootstrap).not.toMatch(/fixture-access|fixture-supervisor|subject|csrf|installation_id/);
  });

  test('an unavailable module leaves visible reload guidance and never claims an empty home', async ({page, context, request}) => {
    if (mode === 'native') await context.addCookies([{name: 'ingress_session', value: 'f'.repeat(128),
      domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
    await page.route('**/assets/*.js', route => route.abort('failed'));
    await page.goto(base(mode) + '/');
    await expect(page.getByText('Loading Domus. If this view does not open, reload it from your Domus installation.', {exact: true})).toBeVisible();
    await expect(page.getByRole('heading', {name: 'Set up your household', exact: true})).toHaveCount(0);
    expect((await stats(request, mode)).counts.households).toBe(0);
  });

  test('an explicit keyboard command persists once, reloads real state, and treats hostile text as text', async ({page, context, request}) => {
    await open(page, context, mode);
    const name = '<img src=x onerror=alert(1)> & family';
    await page.getByLabel('Household name', {exact: true}).fill(name);
    await page.getByLabel('Timezone', {exact: true}).fill('Europe/Madrid');
    await page.getByLabel('Timezone', {exact: true}).press('Enter');
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    await expect(page.getByText(name, {exact: true})).toBeVisible();
    expect((await stats(request, mode)).counts.households).toBe(1);
    expect(await page.locator('domus-app img').count()).toBe(0);
    await page.reload();
    await expect(page.getByText(name, {exact: true})).toBeVisible();
    expect((await stats(request, mode)).counts.households).toBe(1);
  });

  test('a lost committed response recovers the same request without duplicating SQLite effects', async ({page, context, request}) => {
    await open(page, context, mode);
    const sent: {key: string; body: string | null}[] = [];
    let dropped = false;
    await page.route(base(mode) + '/api/v1/household', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      sent.push({key: route.request().headers()['idempotency-key'], body: route.request().postData()});
      if (dropped) return route.continue();
      dropped = true;
      const reply = await route.fetch(); expect(reply.status()).toBe(200);
      await route.abort('connectionreset');
    });
    await create(page);
    await expect(page.getByRole('heading', {name: 'Result not confirmed', exact: true})).toBeVisible();
    const committed = await stats(request, mode);
    expect(committed.counts.households).toBe(1);
    for (const table of ['receipts', 'audit', 'outbox']) expect(committed.counts[table]).toBe(1);
    expect(sent).toHaveLength(1);
    await page.getByRole('button', {name: 'Check previous request', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    expect(sent).toHaveLength(2); expect(sent[1]).toEqual(sent[0]);
    expect(await stats(request, mode)).toEqual(committed);
    await page.reload();
    await expect(page.getByText('Fictional household', {exact: true})).toBeVisible();
    expect(sent).toHaveLength(2); // A reload never resends even a retained request.
    expect(await stats(request, mode)).toEqual(committed);
  });

  test('silent browser storage failure visibly blocks changes before any POST', async ({page, context, request}) => {
    await page.addInitScript(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key !== 'domus.entry.journal.v1') original.call(this, key, value);
      };
    });
    let posts = 0;
    page.on('request', item => {if (item.url().startsWith(base(mode) + '/api/v1/') && item.method() === 'POST') posts++;});
    await open(page, context, mode);
    await expect(page.getByRole('button', {name: 'Create household', exact: true})).toBeDisabled();
    await expect(page.getByText(/Browser recovery storage could not be confirmed/)).toBeVisible();
    expect(posts).toBe(0); expect((await stats(request, mode)).counts.households).toBe(0);
  });

  test('a stale logout intent cannot erase an in-flight committed request or stop recovery', async ({page, context, request}) => {
    await open(page, context, mode);
    let release!: () => void, committed!: () => void;
    const held = new Promise<void>(resolve => {release = resolve;});
    const wrote = new Promise<void>(resolve => {committed = resolve;});
    let intercepted = false;
    await page.route(base(mode) + '/api/v1/household', async route => {
      if (route.request().method() !== 'POST' || intercepted) return route.continue();
      intercepted = true;
      const reply = await route.fetch(); expect(reply.status()).toBe(200);
      committed(); await held; await route.abort('connectionreset');
    });
    try {
      await create(page); await wrote;
      const before = await page.evaluate(key => sessionStorage.getItem(key), journalKey);
      const counts = await stats(request, mode);
      const pending = await page.locator('domus-app').evaluate(element => {
        element.dispatchEvent(new CustomEvent('domus-intent', {detail: {type: 'logout'}, bubbles: true, composed: true}));
        const view = (element as unknown as {view: {phase: string; busy: boolean}}).view;
        return {phase: view.phase, busy: view.busy};
      });
      expect(pending.phase).not.toBe('closed'); expect(pending.busy).toBe(true);
      expect(await page.evaluate(key => sessionStorage.getItem(key), journalKey)).toBe(before);
      expect(await stats(request, mode)).toEqual(counts);
      release();
      await expect(page.getByRole('heading', {name: 'Result not confirmed', exact: true})).toBeVisible();
      await page.getByRole('button', {name: 'Check previous request', exact: true}).click();
      await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
      expect(await stats(request, mode)).toEqual(counts);
    } finally {release();}
  });

  test('close or sign-out retires only owned tab data and preserves server records', async ({page, context, request}) => {
    await open(page, context, mode); await create(page);
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    await page.evaluate(() => {sessionStorage.setItem('fixture.unrelated', 'retained');});
    const before = await stats(request, mode);
    await page.getByRole('button', {name: mode === 'native' ? 'Close this view' : 'Sign out of Domus', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'This view is closed', exact: true})).toBeVisible();
    await expect(page.getByText(mode === 'native' ? /Local access is closed. Home Assistant owns/ :
      'You are signed out of Domus. Household records and server history are retained.', {exact: mode === 'standalone'})).toBeVisible();
    expect(await page.evaluate(key => sessionStorage.getItem(key), journalKey)).toBeNull();
    expect(await page.evaluate(() => sessionStorage.getItem('fixture.unrelated'))).toBe('retained');
    const after = await stats(request, mode);
    expect(after.counts).toEqual(before.counts);
    expect(after.revoked).toBe(mode === 'native' ? 0 : 1);
    if (mode === 'native') expect((await context.cookies()).find(cookie => cookie.name === 'ingress_session')?.value).toBe('f'.repeat(128));
    else expect((await context.cookies()).filter(cookie => cookie.name.includes('session'))).toEqual([]);
  });

  test('Spanish and a narrow viewport remain operable with strict CSP style fallback', async ({page, context, request}, info) => {
    await page.setViewportSize({width: 360, height: 800});
    const violations: string[] = [];
    await page.exposeFunction('fixtureCSPViolation', (value: string) => violations.push(value));
    await page.addInitScript(() => {
      delete (Document.prototype as {adoptedStyleSheets?: unknown}).adoptedStyleSheets;
      document.addEventListener('securitypolicyviolation', event => {
        void (window as unknown as {fixtureCSPViolation(value: string): Promise<void>}).fixtureCSPViolation(event.violatedDirective);
      });
    });
    await open(page, context, mode);
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    await expect(page.getByRole('heading', {name: 'Configura tu hogar', exact: true})).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    await page.getByLabel('Nombre del hogar', {exact: true}).fill('Hogar de prueba');
    await page.getByLabel('Zona horaria', {exact: true}).fill('Europe/Madrid');
    const layout = await page.locator('domus-app').evaluate(element => {
      const styles = [...element.shadowRoot!.querySelectorAll('style')];
      const button = element.shadowRoot!.querySelector('button.primary')!;
      return {styles: styles.map(style => style.nonce), background: getComputedStyle(button).backgroundColor,
        width: document.documentElement.scrollWidth, viewport: innerWidth};
    });
    expect(layout.styles.length).toBeGreaterThan(0);
    expect(layout.styles.every(value => /^[\w-]{32}$/u.test(value))).toBe(true);
    expect(layout.background).not.toBe('rgba(0, 0, 0, 0)');
    expect(layout.width).toBeLessThanOrEqual(layout.viewport);
    expect(violations).toEqual([]);
    await page.screenshot({path: info.outputPath('integrated-es-360.png'), fullPage: true});
    expect((await stats(request, mode)).counts.households).toBe(0);
  });

  test('a verified HA outage preserves local read-only facts and the original deadline', async ({page, context, request}) => {
    await open(page, context, mode); await create(page);
    await expect(page.getByText('Fictional household', {exact: true})).toBeVisible();
    const original = await page.evaluate(() => (document.querySelector('domus-app') as unknown as {
      view: {session: {expiresAt: number}}}).view.session.expiresAt);
    expect((await request.post(origin(mode) + '/__fixture__/identity', {data: {outage: true}})).ok()).toBe(true);
    await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Read-only access', exact: true})).toBeVisible();
    await expect(page.getByText('Fictional household', {exact: true})).toBeVisible();
    expect(await page.evaluate(() => (document.querySelector('domus-app') as unknown as {
      view: {session: {expiresAt: number}}}).view.session.expiresAt)).toBe(original);
    expect((await stats(request, mode)).counts.households).toBe(1);
  });

  test('an ordinary verified account joins only through an explicit pending-membership command', async ({page, context, request}) => {
    await open(page, context, mode); await create(page);
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'b'.repeat(32)}});
    if (mode === 'native') await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
    else {
      await page.getByRole('button', {name: 'Sign out of Domus', exact: true}).click();
      await expect(page.getByText('You are signed out of Domus. Household records and server history are retained.', {exact: true})).toBeVisible();
      await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
      await page.getByRole('link', {name: 'Continue as fixture user'}).click();
    }
    await expect(page.getByRole('heading', {name: 'Join your household', exact: true})).toBeVisible();
    const before = await stats(request, mode);
    expect(before.counts.members).toBe(1);
    await expect(page.getByText('Fictional household', {exact: true})).toHaveCount(0);
    await page.getByRole('button', {name: 'Request membership', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Membership pending', exact: true})).toBeVisible();
    expect((await stats(request, mode)).counts.members).toBe(2);
    await page.reload();
    await expect(page.getByRole('heading', {name: 'Membership pending', exact: true})).toBeVisible();
    expect((await stats(request, mode)).counts.members).toBe(2);
    await expect(page.getByText('Fictional household', {exact: true})).toHaveCount(0);
  });
});

test('standalone starts signed out and never initiates OAuth automatically', async ({page, request}) => {
  await request.post(origin('standalone') + '/__fixture__/reset');
  await open(page, page.context(), 'standalone', false);
  await expect(page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true})).toBeVisible();
  expect(page.url()).toBe(origin('standalone') + '/');
  expect((await stats(request, 'standalone')).counts.households).toBe(0);
});

test('native identity replacement retires the previous person draft even after switching back', async ({page, context, request}) => {
  const mode = 'native';
  await request.post(origin(mode) + '/__fixture__/reset');
  await open(page, context, mode);
  await page.getByLabel('Household name', {exact: true}).fill('Private former account draft');
  await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'b'.repeat(32)}});
  await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Set up your household', exact: true})).toBeVisible();
  await expect(page.getByLabel('Household name', {exact: true})).toHaveCount(0);
  expect(await page.locator('domus-app').innerText()).not.toContain('Private former account draft');
  await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'a'.repeat(32)}});
  await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
  await expect(page.getByLabel('Household name', {exact: true})).toHaveValue('');
  expect((await stats(request, mode)).counts.households).toBe(0);
});
