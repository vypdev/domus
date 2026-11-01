import {expect, test} from '@playwright/test';
import {message} from '../../src/presentation/messages';
import type {MessageKey} from '../../src/presentation/messages';
import type {DomusApp} from '../../src/presentation/domus-app';

const origin = 'http://127.0.0.1:56173';
test.beforeAll(async ({browser}) => {console.info('Catalog Chromium version: ' + browser.version());});
const examples: readonly [string, MessageKey][] = [
  ['loading', 'loading'], ['setup', 'state_unconfigured'], ['joining', 'state_not_enrolled'],
  ['pending', 'state_pending'], ['active', 'state_active'], ['suspended', 'state_suspended'],
  ['archived', 'state_archived'], ['denied', 'state_unconfigured'], ['unavailable', 'state_unavailable'],
  ['read-only', 'state_active'], ['invalid', 'state_unconfigured'], ['uncertain', 'state_active'],
  ['historical', 'state_active'], ['spanish', 'state_unconfigured'],
];
function url(example: string, locale: string, deployment: string) {
  return origin + '/iframe.html?id=domus-household-entry--' + example
    + '&viewMode=story&args=' + encodeURIComponent(`language:${locale};deployment:${deployment}`);
}

for (const [example, key] of examples) {
  test(`built ${example} renders both languages/deployments without server or foreign requests`, async ({page}) => {
    const errors: string[] = [], foreign: string[] = [];
    page.on('pageerror', error => {errors.push(error.message);});
    await page.route('**/*', async route => {
      if (new URL(route.request().url()).origin !== origin) {foreign.push(route.request().url()); await route.abort();}
      else await route.continue();
    });
    for (const [locale, deployment] of [['en', 'native'], ['en', 'standalone'], ['es', 'native'], ['es', 'standalone']] as const) {
      await page.goto(url(example, locale, deployment));
      const app = page.locator('domus-app');
      await expect(app.getByRole('heading', {level: 1})).toHaveText(message(key, locale));
      await expect(app).toHaveAttribute('lang', locale);
      await expect(page.getByText('Fictional interface state.', {exact: false})).toBeVisible();
      if (example === 'pending') await expect(app.getByText(message('body_pending', locale), {exact: true})).toBeVisible();
      if (example === 'historical') await expect(app.getByText(message('historicalBody', locale), {exact: true})).toBeVisible();
      if (example === 'setup' && locale === 'en' && deployment === 'native') await page.screenshot({path: 'test-results/setup-en.png', fullPage: true});
      if (example === 'historical' && locale === 'es' && deployment === 'standalone') await page.screenshot({path: 'test-results/historical-es.png', fullPage: true});
    }
    expect(errors).toEqual([]); expect(foreign).toEqual([]);
  });
}

test('the built form supports actual keyboard submission and retains its draft across locale change', async ({page}) => {
  await page.goto(url('setup', 'en', 'native'));
  await page.locator('domus-app').evaluate(element => {
    const state = window as unknown as {capturedIntents: unknown[]}; state.capturedIntents = [];
    element.addEventListener('domus-intent', event => {state.capturedIntents.push((event as CustomEvent).detail);});
  });
  const app = page.locator('domus-app');
  await app.getByLabel('Household name', {exact: true}).fill('  Maple House  ');
  await app.getByLabel('Timezone', {exact: true}).fill('Europe/Madrid');
  await page.keyboard.press('Tab'); await expect(app.getByRole('button', {name: 'Create household', exact: true})).toBeFocused();
  await page.keyboard.press('Enter');
  expect(await page.evaluate(() => (window as unknown as {capturedIntents: unknown[]}).capturedIntents))
    .toEqual([{type: 'setup', name: '  Maple House  ', timeZone: 'Europe/Madrid'}]);
  await app.getByLabel('Language', {exact: true}).selectOption('es');
  await expect(app.getByRole('heading', {level: 1})).toHaveText('Configura tu hogar');
  await expect(app.getByLabel('Nombre del hogar', {exact: true})).toHaveValue('  Maple House  ');
  await expect(app.getByLabel('Zona horaria', {exact: true})).toHaveValue('Europe/Madrid');
});
test('the built validation state provides actual focus and associated accessible errors', async ({page}) => {
  await page.goto(url('invalid', 'es', 'standalone'));
  const app = page.locator('domus-app'), input = app.getByLabel('Nombre del hogar', {exact: true});
  await expect(input).toBeFocused(); await expect(input).toHaveAttribute('aria-invalid', 'true');
  await expect(input).toHaveAttribute('aria-describedby', 'name-help name-error');
  await expect(app.locator('#name-error')).toBeVisible();
});
test('the built view clears a rapid private edit before rendering a different verified account', async ({page}) => {
  await page.goto(url('setup', 'en', 'standalone'));
  const app = page.locator('domus-app'); await expect(app.getByLabel('Household name', {exact: true})).toBeVisible();
  await app.evaluate(element => {
    const component = element as DomusApp, current = component.view!;
    const name = component.shadowRoot!.querySelector<HTMLInputElement>('#name')!;
    const zone = component.shadowRoot!.querySelector<HTMLInputElement>('#time_zone')!;
    name.value = 'Private prior household'; name.dispatchEvent(new InputEvent('input', {bubbles: true}));
    zone.value = 'Europe/Madrid'; zone.dispatchEvent(new InputEvent('input', {bubbles: true}));
    component.view = {...current, session: {...current.session!, context: {...current.session!.context, subject: 'b'.repeat(32)}}};
  });
  await expect(app.getByLabel('Household name', {exact: true})).toHaveValue('');
  await expect(app.getByLabel('Timezone', {exact: true})).toHaveValue('');
});
test('the built interface fits 360 pixels with light/dark contrast and reduced-motion preferences', async ({page}) => {
  await page.setViewportSize({width: 360, height: 800});
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({colorScheme, reducedMotion: 'reduce'});
    await page.goto(url('setup', 'es', 'native'));
    const app = page.locator('domus-app');
    await expect(app.getByRole('button', {name: 'Crear hogar', exact: true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
    const contrast = await app.locator('button.primary').evaluate(button => {
      const style = getComputedStyle(button);
      function luminance(rgb: string): number {
        const values = rgb.match(/[\d.]+/gu)!.slice(0, 3).map(Number).map(value => {
          const v = value / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
        });
        return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
      }
      const a = luminance(style.color), b = luminance(style.backgroundColor);
      return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    });
    expect(contrast).toBeGreaterThanOrEqual(4.5);
    await page.screenshot({path: `test-results/setup-es-360-${colorScheme}.png`, fullPage: true});
  }
});
