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
async function open(page: Page, context: BrowserContext, mode: Mode, signIn = true, ingressCookie = 'f'.repeat(128)) {
  if (mode === 'native') await context.addCookies([{name: 'ingress_session', value: ingressCookie,
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

  test('closing the browser tab preserves server receipts and a new tab creates no duplicate work', async ({page, context, request}) => {
    await open(page, context, mode); await create(page);
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    const original = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records[0], journalKey);
    const before = await stats(request, mode);
    await page.close();
    const reopened = await context.newPage(), posts: string[] = [];
    try {
      reopened.on('request', item => {if (item.method() === 'POST') posts.push(item.url());});
      expect((await reopened.goto(base(mode) + '/'))?.status()).toBe(200);
      await expect(reopened.getByText('Fictional household', {exact: true})).toBeVisible();
      expect(await reopened.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records, journalKey)).toEqual([]);
      const receipt = await reopened.request.get(base(mode) + '/api/v1/operations/' + original.operationId);
      expect(receipt.status()).toBe(200);
      expect((await receipt.json()).operation_id).toBe(original.operationId);
      expect((await stats(request, mode)).counts).toEqual(before.counts); expect(posts).toEqual([]);
    } finally {await reopened.close();}
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
    await page.locator('details summary').click();
    await expect(page.locator('details dl dd').first()).toHaveText('Configura tu hogar');
    await page.getByLabel('Idioma', {exact: true}).selectOption('en');
    await expect(page.locator('details dl dd').first()).toHaveText('Set up your household');
    await page.getByLabel('Language', {exact: true}).selectOption('es');
    await expect(page.getByLabel('Nombre del hogar', {exact: true})).toHaveValue('Hogar de prueba');
    await expect(page.getByLabel('Zona horaria', {exact: true})).toHaveValue('Europe/Madrid');
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

  test('actual console restoration returns a historical original receipt without recreating its effect', async ({page, context, request}) => {
    await open(page, context, mode);
    expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'snapshot'}})).ok()).toBe(true);
    await create(page);
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    const record = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records[0], journalKey);
    expect((await stats(request, mode)).counts.households).toBe(1);
    expect((await request.post(origin(mode) + '/__fixture__/operator', {data: {action: 'restore'}})).ok()).toBe(true);
    const restored = await stats(request, mode);
    expect(restored.counts.households).toBe(0);
    expect(restored.counts.retained_operations).toBe(1);
    let posts = 0;
    page.on('request', item => {if (item.url() === base(mode) + '/api/v1/household' && item.method() === 'POST') posts++;});
    await page.reload();
    if (mode === 'standalone') {
      await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
      await page.getByRole('link', {name: 'Continue as fixture user'}).click();
    }
    await expect(page.getByRole('heading', {name: 'Set up your household', exact: true})).toBeVisible();
    expect(posts).toBe(0);
    await page.getByRole('button', {name: 'Check previous request', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Previously processed request', exact: true})).toBeVisible();
    await expect(page.getByText('This operation was processed before restoration. Its effect is absent from current state. Review current records before requesting new work.', {exact: true})).toBeVisible();
    const checked = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records[0], journalKey);
    expect(checked).toMatchObject({key: record.key, payload: record.payload, operationId: record.operationId,
      createdAt: record.createdAt, expiresAt: record.expiresAt, stage: 'historical'});
    expect((await stats(request, mode)).counts).toEqual(restored.counts);
    expect(posts).toBe(1);
  });

  for (const channel of ['edge', 'stable'] as const) test(`fresh ${channel} installation retires incompatible requests without replay`, async ({page, context, request}) => {
    await open(page, context, mode); await create(page, 'Private prior installation');
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    const previous = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).context, journalKey);
    await page.evaluate(() => sessionStorage.setItem('fixture.unrelated', 'retained'));
    await request.post(origin(mode) + '/__fixture__/reset', {data: {channel}});
    let posts = 0;
    page.on('request', item => {if (item.url() === base(mode) + '/api/v1/household' && item.method() === 'POST') posts++;});
    await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
    if (mode === 'standalone') {
      await page.getByRole('button', {name: 'Sign in with Home Assistant', exact: true}).click();
      await page.getByRole('link', {name: 'Continue as fixture user'}).click();
    }
    await expect(page.getByRole('heading', {name: 'Set up your household', exact: true})).toBeVisible();
    await expect(page.getByLabel('Household name', {exact: true})).toHaveValue('');
    await expect(page.getByText('Private prior installation', {exact: true})).toHaveCount(0);
    const current = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!), journalKey);
    expect(current.context.installationId).not.toBe(previous.installationId);
    expect(current.context.channel).toBe(channel); expect(current.records).toEqual([]);
    expect(await page.evaluate(() => sessionStorage.getItem('fixture.unrelated'))).toBe('retained');
    expect((await stats(request, mode)).counts.households).toBe(0); expect(posts).toBe(0);
  });

  for (const actors of ['same_account', 'different_accounts'] as const) test(`independent ${actors} setup preserves the singleton and current command authority`, async ({page, context, browser, request}) => {
    await open(page, context, mode);
    const peer = await browser.newContext(), peerPage = await peer.newPage();
    let release!: () => void, arrived!: () => void, count = 0;
    const gate = new Promise<void>(resolve => {release = resolve;});
    const ready = new Promise<void>(resolve => {arrived = resolve;});
    const statuses: number[] = [], keys: string[] = [];
    try {
      if (mode === 'standalone' && actors === 'different_accounts') await request.post(origin(mode) + '/__fixture__/identity', {data: {subject: 'c'.repeat(32)}});
      await open(peerPage, peer, mode, true, (actors === 'different_accounts' ? 'e' : 'd').repeat(128));
      for (const candidate of [page, peerPage]) {
        candidate.on('response', response => {
          if (response.url() === base(mode) + '/api/v1/household' && response.request().method() === 'POST') statuses.push(response.status());
        });
        await candidate.route(base(mode) + '/api/v1/household', async route => {
          if (route.request().method() !== 'POST') return route.continue();
          keys.push(route.request().headers()['idempotency-key']);
          if (++count === 2) arrived();
          await gate; await route.continue();
        });
      }
      await Promise.all([create(page, 'Fictional administrator A'), create(peerPage, 'Fictional administrator C')]);
      await ready; release();
      // An active mapped member gets a conflict; a new unlinked HA admin gains no implicit membership.
      await expect.poll(() => statuses.slice().sort()).toEqual([200, actors === 'same_account' ? 409 : 403]);
      expect(new Set(keys).size).toBe(2);
      const final = await stats(request, mode);
      for (const table of ['households', 'members', 'receipts', 'audit', 'outbox']) expect(final.counts[table], table).toBe(1);
      expect(final.counts.retained_operations).toBe(0); // Current receipts are not rolled-away history.
      await expect.poll(async () => (await Promise.all([page, peerPage].map(candidate => candidate.locator('domus-app').evaluate(element =>
        (element as unknown as {view: {outcome: {kind: string} | null}}).view.outcome?.kind)))).sort()).toEqual(['receipt', 'rejected']);
      const records = await Promise.all([page, peerPage].map(candidate => candidate.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records[0], journalKey)));
      expect(records.map(record => record.stage).sort()).toEqual(['committed', 'rejected']);
      expect(new Set(records.map(record => record.key))).toEqual(new Set(keys));
      await Promise.all([page, peerPage].map(candidate => candidate.getByRole('button', {name: 'Refresh status', exact: true}).click()));
      expect(count).toBe(2); expect((await stats(request, mode)).counts).toEqual(final.counts);
    } finally {release(); await peer.close();}
  });

  test('failed owned-storage clearing closes local access and reports uncertainty without canceling sign-out', async ({page, context, request}) => {
    await open(page, context, mode); await create(page);
    await expect(page.getByRole('heading', {name: 'Request recorded', exact: true})).toBeVisible();
    const record = await page.evaluate(key => sessionStorage.getItem(key), journalKey);
    await page.evaluate(() => {
      sessionStorage.setItem('fixture.unrelated', 'retained');
      const remove = Storage.prototype.removeItem;
      Storage.prototype.removeItem = function(key) {
        if (key === 'domus.entry.journal.v1') throw new DOMException('Fictional denied removal', 'SecurityError');
        remove.call(this, key);
      };
    });
    const before = await stats(request, mode);
    await page.getByRole('button', {name: mode === 'native' ? 'Close this view' : 'Sign out of Domus', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'This view is closed', exact: true})).toBeVisible();
    await expect(page.getByRole('alert')).toHaveText('Owned browser data could not be confirmed as cleared. This view has no active household access.');
    if (mode === 'standalone') await expect(page.getByText('You are signed out of Domus. Household records and server history are retained.', {exact: true})).toBeVisible();
    expect(await page.evaluate(key => sessionStorage.getItem(key), journalKey)).toBe(record);
    expect(await page.evaluate(() => sessionStorage.getItem('fixture.unrelated'))).toBe('retained');
    expect(await page.locator('domus-app').evaluate(element => {
      const view = (element as unknown as {view: {session: unknown; household: unknown; journal: unknown}}).view;
      return [view.session, view.household, view.journal];
    })).toEqual([null, null, null]);
    const after = await stats(request, mode);
    expect(after.counts).toEqual(before.counts); expect(after.revoked).toBe(mode === 'native' ? 0 : 1);
  });

  for (const field of ['origin', 'x-csrf-token'] as const) test(`a forged ${field} is rejected by the actual server before any household effect`, async ({page, context, request}) => {
    await open(page, context, mode);
    let posts = 0;
    await page.route(base(mode) + '/api/v1/household', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      posts++;
      const headers = {...route.request().headers(),
        [field]: field === 'origin' ? 'https://attacker.invalid' : '0'.repeat(64)};
      if (field === 'origin') {
        // Chromium owns Origin; send this raw attack to the actual server and deliver its real denial.
        const response = await route.fetch({headers, maxRedirects: 0});
        expect(response.status()).toBe(403); await route.fulfill({response});
      } else await route.continue({headers});
    });
    await create(page);
    await expect(page.getByRole('heading', {name: 'Request not accepted', exact: true})).toBeVisible();
    await expect(page.getByText('Current access was denied. Ask an administrator to review your permissions.', {exact: true})).toBeVisible();
    const record = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records[0], journalKey);
    expect(record.stage).toBe('rejected'); expect(record.operationId).toBeNull();
    expect(record.payload.name).toBe('Fictional household'); expect(posts).toBe(1);
    for (const count of Object.values((await stats(request, mode)).counts)) expect(count).toBe(0);
  });

  test('loss of the real browser cookie blocks a cached setup grant before POST', async ({page, context, request}) => {
    await open(page, context, mode); await context.clearCookies();
    let posts = 0;
    page.on('request', item => {if (item.url() === base(mode) + '/api/v1/household' && item.method() === 'POST') posts++;});
    await create(page);
    await expect(page.getByRole('heading', {name: 'Verify your access', exact: true})).toBeVisible();
    expect(posts).toBe(0);
    expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).records, journalKey)).toEqual([]);
    expect((await stats(request, mode)).counts.households).toBe(0);
  });

  test('browser wake after the original grace deadline hides local facts and refresh cannot renew it', async ({page, context, request}) => {
    await page.clock.install();
    await open(page, context, mode); await create(page);
    await expect(page.getByText('Fictional household', {exact: true})).toBeVisible();
    await request.post(origin(mode) + '/__fixture__/identity', {data: {outage: true}});
    await page.getByRole('button', {name: 'Refresh status', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Read-only access', exact: true})).toBeVisible();
    const remaining = await page.locator('domus-app').evaluate(element => {
      const session = (element as unknown as {view: {session: {expiresAt: number; serverTime: number}}}).view.session;
      return session.expiresAt - session.serverTime;
    });
    expect(remaining).toBeGreaterThan(0);
    await page.clock.fastForward(remaining + 1001);
    await expect(page.getByRole('heading', {name: 'Verify your access', exact: true})).toBeVisible();
    await expect(page.getByText('Fictional household', {exact: true})).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Refresh status', exact: true})).toHaveCount(0);
    await page.locator('domus-app').evaluate(element => element.dispatchEvent(
      new CustomEvent('domus-intent', {detail: {type: 'refresh'}, bubbles: true, composed: true})));
    await expect(page.getByRole('heading', {name: 'Verify your access', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: 'Create household', exact: true})).toHaveCount(0);
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

test('native rejected human proof loads safe reopening guidance without disclosing household facts', async ({page, context, request}) => {
  const mode = 'native';
  await request.post(origin(mode) + '/__fixture__/reset');
  await open(page, context, mode); await create(page, 'Private existing household');
  await expect(page.getByText('Private existing household', {exact: true})).toBeVisible();
  const before = await stats(request, mode), errors: string[] = [], resources: number[] = [], sessions: number[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.url().startsWith(base(mode) + '/assets/')) resources.push(response.status());
    if (response.url() === base(mode) + '/api/v1/session') sessions.push(response.status());
  });
  expect((await request.post(origin(mode) + '/__fixture__/identity', {data: {rejected: true}})).ok()).toBe(true);
  expect((await page.reload())?.status()).toBe(200);
  await expect(page.getByRole('heading', {name: 'Verify your access', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Reopen Domus', exact: true})).toBeVisible();
  await expect(page.getByText('Private existing household', {exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Create household', exact: true})).toHaveCount(0);
  expect(resources.length).toBeGreaterThan(0); expect(resources.every(status => status === 200)).toBe(true);
  expect(sessions).toEqual([401]); expect(errors).toEqual([]);
  expect((await stats(request, mode)).counts).toEqual(before.counts);
});
