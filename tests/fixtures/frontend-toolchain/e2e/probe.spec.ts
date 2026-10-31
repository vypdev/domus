import {test, expect} from '@playwright/test';
test.beforeEach(async ({browser}, info) => {
  info.annotations.push({type: 'browser', description: `${browser.browserType().name()} ${browser.version()}`});
});
for (const width of [320, 1280]) {
  test(`built Vite entry supports keyboard and fits ${width}px`, async ({page}) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({width, height: 800});
    await page.goto('http://127.0.0.1:56171');
    const button = page.getByRole('button', {name: 'Disabled'});
    await expect(button).toHaveAttribute('aria-pressed', 'false');
    await page.keyboard.press('Tab');
    await expect(button).toBeFocused();
    const box = await button.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press('Enter');
    const enabled = page.getByRole('button', {name: 'Enabled'});
    await expect(enabled).toHaveAttribute('aria-pressed', 'true');
    await expect(enabled).toBeFocused();
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', {name: 'Disabled'})).toHaveAttribute('aria-pressed', 'false');
    expect(errors).toEqual([]);
  });
  test(`built Storybook renders the interactive story at ${width}px`, async ({page}) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({width, height: 800});
    await page.goto('http://127.0.0.1:56172/iframe.html?id=probe-toggle--default&viewMode=story');
    const button = page.getByRole('button', {name: 'Disabled'});
    await button.click();
    await expect(page.getByRole('button', {name: 'Enabled'})).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Space');
    const disabled = page.getByRole('button', {name: 'Disabled'});
    await expect(disabled).toHaveAttribute('aria-pressed', 'false');
    await expect(disabled).toBeFocused();
    const box = await disabled.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    expect(errors).toEqual([]);
  });
}
