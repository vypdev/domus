import {expect, test, vi} from 'vitest';
import {AdministrationError, aliasValue, nextRevision, preferenceValues, revisionValue}
  from '../src/domain/administration';
import {administrationJSON, aliasBody, preferencesBody, responseInteger, responseRevision}
  from '../src/adapters/administration-json';

test.each(['1', '9007199254740991', '9007199254740992', '9007199254740993',
  '9223372036854775806', '9223372036854775807'])(
  'administration revisions preserve the exact decimal value %s', value => {
    expect(revisionValue(value)).toBe(value);
  });

test.each([null, undefined, true, false, 1, 9007199254740992, 1n, {}, [], '', '0', '-1',
  '+1', '01', '1.0', '1e0', ' 1', '1 ', '1\n', '９', '9223372036854775808', '1'.repeat(100)])(
  'ambiguous or out-of-range revision case %# cannot become an exact request', value => {
    expect(() => revisionValue(value)).toThrowError(AdministrationError);
    expect(() => revisionValue(value)).toThrow('invalid_revision');
  });

test('a successor crosses the JavaScript safe boundary exactly and never wraps int64', () => {
  expect(nextRevision(revisionValue('9007199254740992'))).toBe('9007199254740993');
  expect(nextRevision(revisionValue('9223372036854775806'))).toBe('9223372036854775807');
  expect(() => nextRevision(revisionValue('9223372036854775807')))
    .toThrow('revision_exhausted');
});

test.each([null, 'A', '<b>Literal</b>', 'e\u0301', '😀'.repeat(80), '\uFEFFName\uFEFF'])(
  'a supported alias %j is literal data with no identity or permission', value => {
    expect(aliasValue(value)).toBe(value);
  });

test('alias whitespace uses the backend policy without normalizing Unicode text', () => {
  expect(aliasValue('  A\u00a0')).toBe('A');
  expect(aliasValue('\u2003e\u0301\u2003')).toBe('e\u0301');
  expect(aliasValue(' \uFEFFName\uFEFF ')).toBe('\uFEFFName\uFEFF');
});

test.each([undefined, 0, true, {}, [], '', '   ', 'A'.repeat(81), '😀'.repeat(81),
  '\tName', '\nName', 'Name\u0000', 'Name\u007f', 'Name\u0085', '\ud800', '\udfff'])(
  'unsupported alias %j fails before trimming or any request', value => {
    expect(() => aliasValue(value)).toThrow('invalid_alias');
  });

test.each([null, 'en', 'es'] as const)(
  'own preferences accept only the supported locale %s and an exact boolean', locale => {
    for (const summaries of [false, true]) {
      const result = preferenceValues(locale, summaries);
      expect(result).toEqual({locale, routine_participation_summaries: summaries});
      expect(Object.isFrozen(result)).toBe(true);
      expect(Object.keys(result)).toHaveLength(2);
    }
  });

test.each([['EN', true], ['future', false], [undefined, true], [1, true], [null, 0],
  ['es', 'true'], ['en', null]])('unsupported preference values %j fail closed', (locale, summaries) => {
  expect(() => preferenceValues(locale, summaries)).toThrow('invalid_preferences');
});

test('HTTP revision integers are decoded from their original source before Number can round them', () => {
  for (const decimal of ['1', '9007199254740993', '9223372036854775807']) {
    const decoded = administrationJSON('{"revision":' + decimal + '}') as {revision: unknown};
    expect(responseRevision(decoded.revision)).toBe(decimal);
  }
});

test('wire strings or lookalike objects cannot forge a numeric revision', () => {
  for (const body of ['{"revision":"1"}', '{"revision":{"source":"1"}}',
    '{"revision":true}', '{"revision":null}', '{"revision":0}', '{"revision":-1}']) {
    const value = administrationJSON(body) as {revision: unknown};
    expect(() => responseRevision(value.revision)).toThrow('invalid_response');
  }
});

test('integer conversion requires an exact safe number and never converts a numeric string', () => {
  const values = administrationJSON('[0,1,9007199254740991,-1,9007199254740992,"1"]') as unknown[];
  expect(values.slice(0, 3).map(value => responseInteger(value))).toEqual([0, 1, Number.MAX_SAFE_INTEGER]);
  for (const value of values.slice(3)) expect(() => responseInteger(value)).toThrow('invalid_response');
});

test('strings stay inert, escaped keys remain unique and real numeric facts retain their type', () => {
  const raw = '{"name":"value 9007199254740993 \\\"quoted\\\" \\u003Cscript\\u003E", "list":[false,null,1]}';
  const value = administrationJSON(raw) as {name: string; list: unknown[]};
  expect(value.name).toBe('value 9007199254740993 "quoted" <script>');
  expect(value.list.slice(0, 2)).toEqual([false, null]);
  expect(responseInteger(value.list[2])).toBe(1);
});

test.each(['{"revision":1,"revision":2}', '{"revision":1,"revi\\u0073ion":2}',
  '{"revision":1.0}', '{"revision":1e0}', '{"revision":-0}', '{"revision":01}',
  '{"revision":9223372036854775808}', '{"revision":-9223372036854775809}',
  '{"revision":NaN}', '{"revision":Infinity}', '[', '[] true', '{"label":"unterminated',
  '{"label":"unterminated\\',
  '['.repeat(17) + '1' + ']'.repeat(17)])('unsupported JSON case %# fails before coercion', raw => {
  expect(() => administrationJSON(raw)).toThrow('invalid_response');
});

test('the decoder rejects oversized input and requires a string', () => {
  for (const value of [undefined, null, {}, ' '.repeat(65537), '"' + 'é'.repeat(40000) + '"'])
    expect(() => administrationJSON(value)).toThrow('invalid_response');
});

test('an engine without original numeric source fails closed instead of using its rounded Number', () => {
  const original = JSON.parse;
  const stub = vi.spyOn(JSON, 'parse').mockImplementation((raw, reviver) =>
    original(raw, reviver === undefined ? undefined : (key, value) => reviver(key, value)));
  try {
    expect(() => administrationJSON('{"revision":9007199254740993}')).toThrow('invalid_response');
  } finally {stub.mockRestore();}
});

test('HTTP request bodies contain the exact int64 lexeme and only supported owner-independent fields', () => {
  const revision = revisionValue('9007199254740993');
  const alias = aliasBody(revision, '  <b>Literal</b>  ');
  expect(alias).toBe('{"expected_revision":9007199254740993,"alias":"<b>Literal</b>"}');
  expect(aliasBody(revision, null)).toContain('"alias":null');
  const preferences = preferencesBody(revision, 'es', false);
  expect(preferences).toBe('{"expected_revision":9007199254740993,"locale":"es","routine_participation_summaries":false}');
  const decoded = administrationJSON(preferences) as {expected_revision: unknown};
  expect(responseRevision(decoded.expected_revision)).toBe(revision);
  expect(JSON.parse(aliasBody(revisionValue('1'), '"\\'))).toEqual({expected_revision: 1, alias: '"\\'});
});

test.each([0x20,0xa0,0x1680,...Array.from({length:11},(_unused,index)=>0x2000+index),0x2028,0x2029,0x202f,0x205f,0x3000].map(codepoint=>({
  codepoint,label:'U+'+codepoint.toString(16).toUpperCase().padStart(4,'0')
})))('household-admin-C25: exact astral alias boundary after whitespace $label',({codepoint})=>{
  const marker=String.fromCodePoint(codepoint),exact='😀'.repeat(80);
  expect(aliasValue(marker+exact+marker)).toBe(exact);
  expect(()=>aliasValue(marker+exact+'😀'+marker)).toThrow('invalid_alias');
});
