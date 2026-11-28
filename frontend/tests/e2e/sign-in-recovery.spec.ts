import {expect, test} from '@playwright/test';
import type {APIRequestContext, BrowserContext, Page} from '@playwright/test';

type Mode = 'native' | 'standalone';
const origin = (mode: Mode) => `http://127.0.0.1:${mode === 'native' ? 56174 : 56175}`;
const base = (mode: Mode) => origin(mode) + (mode === 'native'
  ? '/api/hassio_ingress/fixture_domus_supervisor_1234567890' : '');
const words = {
  en: {signIn: 'Sign in with Home Assistant', name: 'Household name', zone: 'Timezone',
    create: 'Create household', home: 'Your household', logout: 'Sign out of Domus',
    recovery: 'Sign-in was not completed', retained: 'Household records are retained'},
  es: {signIn: 'Iniciar sesión con Home Assistant', name: 'Nombre del hogar', zone: 'Zona horaria',
    create: 'Crear hogar', home: 'Tu hogar', logout: 'Cerrar sesión en Domus',
    recovery: 'No se ha completado el inicio de sesión', retained: 'Los registros del hogar se conservan'},
} as const;

async function reset(request: APIRequestContext, mode: Mode) {
  if (process.env.DOMUS_BROWSER_IMAGE) {
    const image = await request.get(origin(mode) + '/__fixture__/image');
    expect(image.status()).toBe(200);
    expect(await image.json()).toEqual({source_commit: process.env.DOMUS_TEST_SOURCE_COMMIT,
      architecture: process.env.DOMUS_TEST_ARCH, image_id: expect.stringMatching(/^sha256:[a-f0-9]{64}$/u), mode});
  }
  expect((await request.post(origin(mode) + '/__fixture__/reset')).ok()).toBe(true);
}
const statistics = async (request: APIRequestContext, mode: Mode) =>
  (await request.get(origin(mode) + '/__fixture__/stats')).json();

async function household(page: Page, context: BrowserContext, mode: Mode, locale: keyof typeof words) {
  const text = words[locale];
  if (mode === 'native') await context.addCookies([{name: 'ingress_session', value: 'f'.repeat(128),
    domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict'}]);
  await page.goto(base(mode) + '/#household');
  if (mode === 'standalone') {
    await page.getByRole('button', {name: text.signIn, exact: true}).click();
    await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).click();
  }
  await page.getByLabel(text.name, {exact: true}).fill('QA 178 preserved household');
  await page.getByLabel(text.zone, {exact: true}).fill('Europe/Madrid');
  await page.getByRole('button', {name: text.create, exact: true}).click();
  await expect(page.getByRole('heading', {name: text.home, level: 1, exact: true})).toBeVisible();
}

for (const locale of ['en', 'es'] as const) test.describe('standalone sign-in recovery ' + locale, () => {
  test.use({locale: locale === 'es' ? 'es-ES' : 'en-US',
    viewport: locale === 'es' ? {width: 390, height: 844} : {width: 1280, height: 900},
    isMobile: locale === 'es', hasTouch: locale === 'es'});
  test.beforeEach(async ({request}) => reset(request, 'standalone'));
  test('an invalid callback returns localized guidance and only a deliberate fresh attempt signs in', async ({page, context, request}, info) => {
    const text = words[locale];
    await household(page, context, 'standalone', locale);
    await page.getByRole('button', {name: text.logout, exact: true}).click();
    const signIn = page.getByRole('button', {name: text.signIn, exact: true});
    await expect(signIn).toBeEnabled(); await signIn.click();
    await expect(page.getByRole('heading', {name: 'Fictional Home Assistant', exact: true})).toBeVisible();
    const continuation = page.getByRole('link', {name: 'Continue as fixture user', exact: true});
    const callback = new URL((await continuation.getAttribute('href'))!, page.url());
    expect(callback.origin).toBe(origin('standalone'));
    expect(callback.pathname).toBe('/api/v1/auth/callback');
    expect(callback.searchParams.has('state')).toBe(true); expect(callback.searchParams.has('code')).toBe(true);
    const bindings = (await context.cookies(origin('standalone'))).filter(cookie => cookie.name.endsWith('-browser'));
    expect(bindings).toHaveLength(1);
    // Retire only this disposable browser binding; never change the server clock or installed image.
    await context.clearCookies({name: bindings[0].name, domain: bindings[0].domain, path: bindings[0].path});
    const before = await statistics(request, 'standalone');
    await continuation.click();
    await expect(page).toHaveURL(origin('standalone') + '/#sign-in-recovery');
    await expect(page.getByRole('heading', {name: text.recovery, level: 1, exact: true})).toBeVisible();
    await expect(page.locator('domus-app').locator('#overview > .intro')).toContainText(text.retained);
    await expect(signIn).toHaveCount(1); await expect(signIn).toBeFocused();
    expect((await page.request.get(origin('standalone') + '/api/v1/session')).status()).toBe(401);
    expect(await statistics(request, 'standalone')).toEqual(before);
    const rendered = await page.locator('domus-app').evaluate(element => element.shadowRoot!.textContent);
    expect(rendered).not.toContain(callback.searchParams.get('state')!);
    expect(rendered).not.toContain(callback.searchParams.get('code')!);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await info.attach('recovery-' + locale, {body: await page.screenshot({fullPage: true}), contentType: 'image/png'});
    if (locale === 'en') await page.keyboard.press('Enter');
    else await signIn.tap();
    await expect(page.getByRole('heading', {name: 'Fictional Home Assistant', exact: true})).toBeVisible();
    if (locale === 'en') {await page.keyboard.press('Tab'); await page.keyboard.press('Enter');}
    else await page.getByRole('link', {name: 'Continue as fixture user', exact: true}).tap();
    await expect(page.getByRole('heading', {name: text.home, level: 1, exact: true})).toBeVisible();
    await expect(page.getByText('QA 178 preserved household', {exact: true})).toBeVisible();
    expect((await page.request.get(origin('standalone') + '/api/v1/session')).status()).toBe(200);
    expect((await statistics(request, 'standalone')).counts).toEqual(before.counts);
  });
});

for (const mode of ['native', 'standalone'] as const) test.describe('public recovery marker ' + mode, () => {
  test.beforeEach(async ({request}) => reset(request, mode));
  test('a public marker retains current verified access and requests no household changes or sign-in', async ({page, context, request}) => {
    await household(page, context, mode, 'en');
    const before = await statistics(request, mode), writes: string[] = [], signIns: string[] = [];
    page.on('request', item => {
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(item.method())) writes.push(item.url());
      if (/\/api\/v1\/auth\/(start|callback|logout)(?:[?#]|$)/u.test(item.url())) signIns.push(item.url());
    });
    await page.goto(base(mode) + '/#sign-in-recovery');
    await expect(page.getByRole('heading', {name: 'Your household', level: 1, exact: true})).toBeVisible();
    await expect(page.getByRole('heading', {name: 'Sign-in was not completed', exact: true})).toHaveCount(0);
    await expect(page.getByText('QA 178 preserved household', {exact: true})).toBeVisible();
    expect((await page.request.get(base(mode) + '/api/v1/session')).status()).toBe(200);
    expect(writes).toEqual([]); expect(signIns).toEqual([]);
    expect((await statistics(request, mode)).counts).toEqual(before.counts);
  });
});
