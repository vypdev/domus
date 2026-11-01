import {afterEach, expect, test, vi} from 'vitest';
import {SessionJournal, ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import {JournalStorageError} from '../src/application/ports';
import {JournalError, JOURNAL_LIFETIME} from '../src/domain/journal';
import type {JournalContext} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const command = {action: 'enroll' as const, payload: {expected_revision: 0 as const}};
function fixture() {
  const values = new Map<string, string>();
  const storage = {getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {values.set(key, value);}),
    removeItem: vi.fn((key: string) => {values.delete(key);})};
  return {values, storage, journal: new SessionJournal(storage)};
}
afterEach(() => {sessionStorage.removeItem(ENTRY_JOURNAL_KEY); sessionStorage.removeItem('domus-journal-test-unrelated');});

test('C24: first opening establishes/readbacks only the owned key, without a server effect', () => {
  const f = fixture(); f.values.set('unrelated', 'keep');
  const opened = f.journal.open(context, 1000);
  expect(opened.records).toEqual([]);
  expect(JSON.parse(f.values.get(ENTRY_JOURNAL_KEY)!)).toEqual(opened);
  expect(f.values.get('unrelated')).toBe('keep');
  expect(f.storage.setItem).toHaveBeenCalledTimes(1);
  expect(f.storage.getItem.mock.calls.every(([key]) => key === ENTRY_JOURNAL_KEY)).toBe(true);
});

test('C07/C24: prepare, reopen, uncertain and historical outcomes retain the exact original', () => {
  const f = fixture(); f.journal.open(context, 1000);
  const original = f.journal.prepare('key', command, 1000).records[0];
  f.journal.detach(); expect(() => f.journal.prepare('other', command, 1001)).toThrow('journal_not_open');
  f.journal.open(context, 1100);
  expect(f.journal.record('key', {stage: 'uncertain', operationId: null}, 1200).records[0])
    .toEqual({...original, stage: 'uncertain'});
  expect(f.journal.record('key', {stage: 'historical', operationId: 'op-1'}, 1300).records[0])
    .toEqual({...original, stage: 'historical', operationId: 'op-1'});
  expect(f.journal.forget('key', 1400).records).toEqual([]);
});

test.each(['getItem', 'setItem', 'removeItem'] as const)('C24/C42: provider %s error is safe and drops memory', method => {
  const f = fixture(); f.journal.open(context, 1000);
  f.storage[method].mockImplementation(() => {throw new Error('secret-provider-detail');});
  const run = method === 'removeItem' ? () => f.journal.clear() : () => f.journal.prepare('key', command, 1100);
  expect(run).toThrow(JournalStorageError); expect(run).not.toThrow('secret-provider-detail');
  expect(() => f.journal.prepare('again', command, 1100)).toThrow('journal_not_open');
});

test('missing storage capability cannot open, clear or grant a usable handle', () => {
  const journal = new SessionJournal(undefined);
  expect(() => journal.open(context, 1000)).toThrow('storage_unavailable');
  expect(() => journal.clear()).toThrow('storage_unavailable');
  expect(() => journal.prepare('key', command, 1000)).toThrow('journal_not_open');
});

test.each([undefined, 4, {}])('malformed storage return %j is not coerced into journal data', raw => {
  const f = fixture(); f.storage.getItem.mockReturnValueOnce(raw as never);
  expect(() => f.journal.open(context, 1000)).toThrow('storage_unavailable');
  expect(f.storage.setItem).not.toHaveBeenCalled();
});

test('a failed post-receipt write cannot replace the original persisted request or the caller receipt', () => {
  const f = fixture(); f.journal.open(context, 1000);
  const original = f.journal.prepare('key', command, 1000).records[0];
  const receipt = Object.freeze({stage: 'committed' as const, operationId: 'op-original'});
  f.storage.setItem.mockImplementationOnce(() => {throw new Error('write failed');});
  expect(() => f.journal.record('key', receipt, 1100)).toThrow('storage_unavailable');
  expect(receipt).toEqual({stage: 'committed', operationId: 'op-original'});
  expect(f.journal.open(context, 1200).records).toEqual([original]);
});

test('failed context replacement exposes no old record and invalidates the old handle', () => {
  const f = fixture(); f.journal.open(context, 1000); f.journal.prepare('old-key', command, 1000);
  f.storage.setItem.mockImplementationOnce(() => {});
  expect(() => f.journal.open({...context, channel: 'stable'}, 1100)).toThrow('storage_unconfirmed');
  expect(() => f.journal.prepare('new-key', command, 1100)).toThrow('journal_not_open');
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toContain('old-key');
});

test.each(['not-json', '{}', '{"version":2}', ' {"version":1}',
  '{"version":1,"version":2}', '{"version":1.0}', '{"version":1,"context":{"a":1,"a":2}}'])(
  'C05: corrupt/noncanonical input %s is retained and never used', raw => {
    const f = fixture(); f.values.set(ENTRY_JOURNAL_KEY, raw);
    expect(() => f.journal.open(context, 1000)).toThrow(JournalError);
    expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(raw); expect(f.storage.setItem).not.toHaveBeenCalled();
    expect(() => f.journal.prepare('key', command, 1000)).toThrow('journal_not_open');
  },
);

test.each(['x'.repeat(65537), '🏠'.repeat(20000)])('C25: oversized UTF-8 input is bounded before JSON parsing', raw => {
  const f = fixture(); f.values.set(ENTRY_JOURNAL_KEY, raw);
  expect(() => f.journal.open(context, 1000)).toThrow('journal_too_large');
  expect(f.storage.setItem).not.toHaveBeenCalled();
});

test('canonical numeric/duplicate-key checks apply inside original payloads too', () => {
  const f = fixture(); f.journal.open(context, 1000); f.journal.prepare('key', command, 1000);
  for (const raw of [f.values.get(ENTRY_JOURNAL_KEY)!.replace('"expected_revision":0', '"expected_revision":0,"expected_revision":0'),
    f.values.get(ENTRY_JOURNAL_KEY)!.replace('"observedAt":1000', '"observedAt":1e3')]) {
    f.values.set(ENTRY_JOURNAL_KEY, raw);
    expect(() => f.journal.open(context, 1000)).toThrow('invalid_journal');
  }
});

test('C41: changed subject clears old local content only after confirmed write', () => {
  const f = fixture(); f.journal.open(context, 1000); f.journal.prepare('private-old-key', command, 1000);
  const result = f.journal.open({...context, subject: 'another'}, 1100);
  expect(result.records).toEqual([]);
  expect(f.values.get(ENTRY_JOURNAL_KEY)).not.toContain('private-old-key');
});

test('C24: silent writes or unverifiable readback never report persistence success', () => {
  const f = fixture(); f.journal.open(context, 1000); const before = f.values.get(ENTRY_JOURNAL_KEY);
  f.storage.setItem.mockImplementation(() => {});
  expect(() => f.journal.prepare('key', command, 1100)).toThrow('storage_unconfirmed');
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe(before);
  expect(() => f.journal.prepare('next', command, 1100)).toThrow('journal_not_open');
});

test('external storage replacement and disappearance invalidate an opened handle', () => {
  for (const replacement of [null, '{}']) {
    const f = fixture(); f.journal.open(context, 1000);
    if (replacement === null) f.values.delete(ENTRY_JOURNAL_KEY); else f.values.set(ENTRY_JOURNAL_KEY, replacement);
    expect(() => f.journal.prepare('key', command, 1100)).toThrow('storage_changed');
    expect(f.storage.setItem).toHaveBeenCalledTimes(1);
  }
});

test('a change during opening is detected before overwriting it', () => {
  const f = fixture(); f.storage.getItem.mockReturnValueOnce(null).mockReturnValueOnce('{}');
  expect(() => f.journal.open(context, 1000)).toThrow('storage_changed');
  expect(f.storage.setItem).not.toHaveBeenCalled();
});

test('C06: expiry prunes local records but a backward observation blocks reopening', () => {
  const f = fixture(); f.journal.open(context, 1000); f.journal.prepare('key', command, 1000);
  expect(() => f.journal.open(context, 999)).toThrow('invalid_journal_time');
  expect(f.journal.open(context, 1000 + JOURNAL_LIFETIME).records).toEqual([]);
});

test('C42: failed clear drops memory, preserves truthful uncertainty and touches no other key', () => {
  const f = fixture(); f.journal.open(context, 1000); f.values.set('other', 'retained');
  f.storage.removeItem.mockImplementation(() => {});
  expect(() => f.journal.clear()).toThrow('storage_unconfirmed');
  expect(() => f.journal.prepare('key', command, 1000)).toThrow('journal_not_open');
  expect(f.values.get('other')).toBe('retained');
});

test('real isolated browser sessionStorage supports reload and owned-only cleanup', () => {
  const journal = new SessionJournal(sessionStorage);
  sessionStorage.setItem('domus-journal-test-unrelated', 'keep');
  journal.open(context, 1000); const original = journal.prepare('key', command, 1000);
  const reloaded = new SessionJournal(sessionStorage);
  expect(reloaded.open(context, 1100).records).toEqual(original.records);
  reloaded.clear(); expect(sessionStorage.getItem(ENTRY_JOURNAL_KEY)).toBeNull();
  expect(sessionStorage.getItem('domus-journal-test-unrelated')).toBe('keep');
});
