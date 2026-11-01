import {expect, test} from 'vitest';
import {BrowserEntropy, BrowserNavigation, ServerClock} from '../src/adapters/browser-capabilities';
import type {EntryEndpoint} from '../src/adapters/http-values';

const standalone: EntryEndpoint = {origin: 'https://domus.example', deployment: 'standalone', applicationBase: '/'};
const native: EntryEndpoint = {...standalone, deployment: 'native', applicationBase: '/api/hassio_ingress/abcdefghijklmnop/'};

test('a server anchor is required; a failed premature read can be followed by verified proof', () => {
  const clock = new ServerClock(() => 4.5);
  expect(() => clock.now()).toThrow('clock_unavailable');
  clock.anchor(1000); expect(clock.now()).toBe(1000);
});
test('fractional monotonic elapsed time advances integer epoch milliseconds without wall-clock input', () => {
  let elapsed = 12.25; const clock = new ServerClock(() => elapsed);
  clock.anchor(1000); elapsed = 13.24; expect(clock.now()).toBe(1000);
  elapsed = 13.25; expect(clock.now()).toBe(1001);
  elapsed = 5012.25; expect(clock.now()).toBe(6000);
});
test('fresh proof cannot rewind the observed clock or add a new lease', () => {
  let elapsed = 0; const clock = new ServerClock(() => elapsed); clock.anchor(1000);
  elapsed = 250; expect(clock.now()).toBe(1250);
  clock.anchor(1100); expect(clock.now()).toBe(1250);
  elapsed = 260; expect(clock.now()).toBe(1260);
  clock.anchor(2000); expect(clock.now()).toBe(2000);
});
test.each([-1, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])('invalid monotonic sample %s poisons the page clock', value => {
  let elapsed = 0; const clock = new ServerClock(() => elapsed); clock.anchor(1000);
  elapsed = value; expect(() => clock.now()).toThrow('clock_unavailable');
  elapsed = 2; expect(() => clock.anchor(2000)).toThrow('clock_unavailable');
  expect(() => clock.now()).toThrow('clock_unavailable');
});
test.each([-1, NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1])('invalid server anchor %s fails closed', value => {
  const clock = new ServerClock(() => 0);
  expect(() => clock.anchor(value)).toThrow('clock_unavailable');
});
test('a monotonic regression fails even when a new server anchor would otherwise hide it', () => {
  let elapsed = 10; const clock = new ServerClock(() => elapsed); clock.anchor(1000);
  elapsed = 11; clock.now(); elapsed = 10.5;
  expect(() => clock.anchor(2000)).toThrow('clock_unavailable');
});
test('a throwing elapsed provider is replaced by bounded failure and cannot silently recover', () => {
  let fail = true; const clock = new ServerClock(() => {if (fail) throw new Error('private provider detail'); return 0;});
  expect(() => clock.anchor(1000)).toThrow('clock_unavailable');
  fail = false; expect(() => clock.anchor(1001)).toThrow('clock_unavailable');
});
test('integer overflow while reading or reanchoring never wraps or extends time', () => {
  for (const reanchor of [false, true]) {
    let elapsed = 0; const clock = new ServerClock(() => elapsed); clock.anchor(Number.MAX_SAFE_INTEGER);
    elapsed = 1;
    expect(() => reanchor ? clock.anchor(1000) : clock.now()).toThrow('clock_unavailable');
  }
});
test('the browser performance capability works with an actual server time', () => {
  const clock = new ServerClock(); clock.anchor(1_800_000_000_000);
  expect(clock.now()).toBeGreaterThanOrEqual(1_800_000_000_000);
});
test('request keys encode exactly the supplied 128 bits without timestamp or normalization', () => {
  const entropy = new BrowserEntropy(bytes => {bytes.set(Array.from({length: 16}, (_, i) => i * 17)); return bytes;});
  expect(entropy.requestKey()).toBe('req_00112233445566778899aabbccddeeff');
});
test('the actual browser cryptographic provider returns distinct bounded request keys', () => {
  const entropy = new BrowserEntropy(); const first = entropy.requestKey(), second = entropy.requestKey();
  expect(first).toMatch(/^req_[a-f0-9]{32}$/u); expect(second).toMatch(/^req_[a-f0-9]{32}$/u);
  expect(first).not.toBe(second);
});
test('entropy failure has no weak fallback and hides provider diagnostics', () => {
  const entropy = new BrowserEntropy(() => {throw new Error('private random-provider detail');});
  expect(() => entropy.requestKey()).toThrow('entropy_unavailable');
});
test('a provider returning a different array is not accepted as the reviewed browser capability', () => {
  expect(() => new BrowserEntropy(() => new Uint8Array(16)).requestKey()).toThrow('entropy_unavailable');
});
test('standalone sign-in and reopen use only the fixed root routes', () => {
  const paths: string[] = []; const navigation = new BrowserNavigation(standalone, path => {paths.push(path);});
  navigation.signIn(); navigation.reopen(); expect(paths).toEqual(['/api/v1/auth/start', '/']);
});
test('native reopen stays under its accepted prefix and cannot start standalone OAuth', () => {
  const paths: string[] = []; const navigation = new BrowserNavigation(native, path => {paths.push(path);});
  expect(() => navigation.signIn()).toThrow('forbidden'); navigation.reopen();
  expect(paths).toEqual([native.applicationBase]);
});
test('navigation captures a validated immutable target and has no arbitrary redirect argument', () => {
  const target = {...standalone}; const paths: string[] = [];
  const navigation = new BrowserNavigation(target, path => {paths.push(path);});
  target.applicationBase = '//attacker.example/'; navigation.reopen();
  expect(paths).toEqual(['/']);
  expect(() => new BrowserNavigation({...native, applicationBase: '/../'}, () => {})).toThrow('invalid_response');
});
test('browser navigation refusal exposes a bounded failure, without another destination', () => {
  const paths: string[] = [];
  const navigation = new BrowserNavigation(standalone, path => {paths.push(path); throw new Error('private provider details');});
  expect(() => navigation.signIn()).toThrow('unavailable');
  expect(paths).toEqual(['/api/v1/auth/start']);
});
