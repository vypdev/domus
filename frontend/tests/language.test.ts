import {expect, test} from 'vitest';
import {instant, language, message, messageKeys} from '../src/presentation/messages';

test.each([
  ['es', 'en-US', 'es'], ['en', 'es-ES', 'en'], ['ES-mx', 'en', 'es'],
  [null, 'es-ES', 'es'], [undefined, 'en-GB', 'en'], ['fr', 'es', 'es'],
  ['fr', 'de', 'en'], [null, null, 'en'], [42, {}, 'en'], ['<script>', 'es_es', 'en'],
])('explicit supported choice %s, browser %s resolves to %s', (explicit, browser, expected) => {
  expect(language(explicit, browser)).toBe(expected);
});
test('both owned catalogs cover every stable key, while a missing localized key falls back to English', () => {
  expect(Object.isFrozen(messageKeys)).toBe(true);
  expect(messageKeys.length).toBeGreaterThan(80);
  for (const key of messageKeys) {
    expect(message(key, 'en').trim().length).toBeGreaterThan(0);
    expect(message(key, 'es').trim().length).toBeGreaterThan(0);
  }
  expect(message('create', 'es')).toBe('Crear hogar');
  expect(message('create', 'es', {})).toBe('Create household');
  expect(message('create', 'en', {create: 'Ignored override'})).toBe('Create household');
});
test('original deadlines are shown in UTC and invalid dates stay safe in both locales', () => {
  expect(instant(1_800_000_000_000, 'en')).toContain('2027');
  expect(instant(1_800_000_000_000, 'es')).toContain('UTC');
  expect(instant(Number.MAX_SAFE_INTEGER, 'en')).toBe('Time unavailable');
  expect(instant(NaN, 'es')).toBe('Hora no disponible');
});
