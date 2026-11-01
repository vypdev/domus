import {expect, test} from 'vitest';
import {bootstrap} from '../src/adapters/bootstrap';

const base = '/api/hassio_ingress/abcdefghijklmnop/';
const native = {version: 1, deployment: 'native', application_base: base, style_nonce: 'a'.repeat(32)};
const standalone = {...native, deployment: 'standalone', application_base: '/'};
test('standalone bootstrap derives actual origin and grants no identity or API authority', () => {
  const result = bootstrap(JSON.stringify(standalone), 'https://domus.example/');
  expect(result).toEqual({target: {origin: 'https://domus.example', deployment: 'standalone', applicationBase: '/'}, styleNonce: 'a'.repeat(32)});
  expect(Object.isFrozen(result)).toBe(true); expect(Object.isFrozen(result.target)).toBe(true);
});
test('native accepts only the exact public root with or without its trailing separator', () => {
  for (const path of [base, base.slice(0, -1)]) {
    expect(bootstrap(JSON.stringify(native), 'http://homeassistant.local:8123' + path).target.applicationBase).toBe(base);
  }
});
test('an unused fragment cannot replace the endpoint, identity, deployment or base', () => {
  expect(bootstrap(JSON.stringify(native), 'https://ha.example' + base + '#endpoint=https://foreign.invalid/').target.origin).toBe('https://ha.example');
});
test.each([undefined, null, {}, '', '[]', '{}', '{bad', 'x'.repeat(4097), '🏠'.repeat(1100)])(
  'malformed or oversized bootstrap %s fails closed', raw => {
    expect(() => bootstrap(raw, 'https://domus.example/')).toThrow('invalid_response');
  });
test.each([
  {...standalone, version: 2}, {...standalone, installation_id: 'invented'},
  {...standalone, origin: 'https://foreign.invalid'}, {...standalone, ha_user_id: 'a'.repeat(32)},
  {...standalone, application_base: '//foreign.invalid/'}, {...standalone, deployment: 'preview'},
  {...standalone, style_nonce: 'x'}, {...standalone, style_nonce: '" onload="alert(1)'},
  {...standalone, style_nonce: 1}, {...standalone, application_base: base},
])('invalid closed bootstrap fields fail before any capability is constructed', value => {
  expect(() => bootstrap(JSON.stringify(value), 'https://domus.example/')).toThrow('invalid_response');
});
test.each([
  null, {}, 'not a URL', 'file:///tmp/index.html', 'https://name:password@domus.example/',
  'https://domus.example/?endpoint=https://foreign.invalid', 'https://domus.example/other',
  'https://domus.example/' + 'x'.repeat(4096),
])('unsupported page URL %s cannot become a trusted endpoint', pageURL => {
  expect(() => bootstrap(JSON.stringify(standalone), pageURL)).toThrow('invalid_response');
});
test.each([base + 'extra', '/', '/api/hassio_ingress/different-token-value/', base.replace('abcdefghijklmnop', '%61bcdefghijklmnop')])(
  'a mismatched native location %s is not accepted', path => {
    expect(() => bootstrap(JSON.stringify(native), 'https://ha.example' + path)).toThrow('invalid_response');
  });
test('duplicate bootstrap keys are rejected rather than choosing the last deployment', () => {
  expect(() => bootstrap(JSON.stringify(standalone).replace('"version":1', '"version":1,"version":1'), 'https://domus.example/'))
    .toThrow('invalid_response');
});
