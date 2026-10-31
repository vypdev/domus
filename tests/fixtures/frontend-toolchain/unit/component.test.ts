import {afterEach, expect, test} from 'vitest';
import '../src/probe-toggle';
import type {ProbeToggle} from '../src/probe-toggle';
let element: ProbeToggle;
const listeners = new AbortController();
afterEach(() => { element.remove(); listeners.abort(); });
test('Lit renders both states and dispatches the actual composed events', async () => {
  element = document.createElement('probe-toggle');
  const events: boolean[] = [];
  document.body.addEventListener('probe-change', event => {
    expect(event.target).toBe(element);
    expect(event.bubbles).toBe(true);
    expect(event.composed).toBe(true);
    events.push(event.detail);
  }, {signal: listeners.signal});
  document.body.append(element);
  await element.updateComplete;
  const button = element.shadowRoot!.querySelector('button')!;
  expect(button.textContent).toBe('Disabled');
  expect(button.getAttribute('aria-pressed')).toBe('false');
  button.click(); await element.updateComplete;
  expect(button.textContent).toBe('Enabled');
  expect(button.getAttribute('aria-pressed')).toBe('true');
  button.click(); await element.updateComplete;
  expect(button.textContent).toBe('Disabled');
  expect(events).toEqual([true, false]);
});
