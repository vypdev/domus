import {afterEach, expect, test, vi} from 'vitest';
import {AdministrationSessionJournal, ADMINISTRATION_JOURNAL_KEY} from '../src/adapters/administration-journal';
import {ENTRY_JOURNAL_KEY} from '../src/adapters/session-journal';
import {administrationCommand} from '../src/domain/administration-commands';
import {JournalStorageError} from '../src/application/ports';
import type {JournalContext} from '../src/domain/journal';

const context: JournalContext = {installationId: '01234567-89ab-cdef-0123-456789abcdef',
  channel: 'edge', subject: 'a'.repeat(32)};
const other = {...context, subject: 'b'.repeat(32)};
const command = administrationCommand({action: 'member.preferences.update', payload: {
  expected_revision: '9007199254740993', locale: 'es', routine_participation_summaries: false}});
function fixture() {
  const values = new Map<string, string>([[ENTRY_JOURNAL_KEY, 'entry original'], ['unrelated', 'keep']]);
  const storage = {getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {values.set(key, value);}), removeItem: vi.fn()};
  return {values, storage, journal: new AdministrationSessionJournal(storage)};
}
afterEach(() => sessionStorage.removeItem(ADMINISTRATION_JOURNAL_KEY));

test('the physical administration namespace is separate; original revisions remain decimal text', () => {
  const f = fixture();
  f.journal.open(context, 1000);
  const original = f.journal.prepare('key', command, 1000).records[0];
  const encoded = f.values.get(ADMINISTRATION_JOURNAL_KEY)!;
  expect(encoded).toContain('"expected_revision":"9007199254740993"');
  expect(JSON.parse(encoded).namespace).toBe('administration');
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe('entry original');
  expect(f.values.get('unrelated')).toBe('keep');
  expect(f.storage.getItem.mock.calls.every(([key]) => key === ADMINISTRATION_JOURNAL_KEY)).toBe(true);
  f.journal.detach();
  expect(() => f.journal.prepare('replacement', command, 1001)).toThrow('journal_not_open');
  expect(f.journal.open(context, 1100).records).toEqual([original]);
  expect(f.journal.record('key', {stage: 'uncertain', operationId: null}, 1200).records[0]).toEqual({...original, stage: 'uncertain'});
  f.journal.record('key', {stage: 'historical', operationId: 'op'}, 1300);
  expect(f.journal.forget('key', 1400).records).toEqual([]);
  expect(f.storage.removeItem).not.toHaveBeenCalled();
});

test('account/channel/installation switches hide old private requests without deleting them', () => {
  const f = fixture(); f.journal.open(context, 1000);
  const original = f.journal.prepare('key', command, 1000).records[0];
  for (const next of [other, {...context, channel: 'stable' as const},
    {...context, installationId: '11111111-1111-1111-1111-111111111111'}]) {
    const view = f.journal.open(next, 1100);
    expect(view.records).toEqual([]);
    expect(JSON.stringify(view)).not.toContain('routine_participation_summaries');
    expect(() => f.journal.record('key', {stage: 'committed', operationId: 'op'}, 1100)).toThrow('request_not_found');
  }
  expect(f.journal.open(context, 1200).records).toEqual([original]);
  f.journal.open(other, 1200); f.journal.prepare('key', command, 1200);
  f.journal.record('key', {stage: 'rejected', operationId: null}, 1300); f.journal.forget('key', 1400);
  expect(f.journal.open(context, 1500).records).toEqual([original]);
});

test.each(['getItem', 'setItem'] as const)('provider %s failures drop memory and expose no original exception', method => {
  const f = fixture(); f.journal.open(context, 1000);
  f.storage[method].mockImplementationOnce(() => {throw new Error('provider secret');});
  expect(() => f.journal.prepare('key', command, 1100)).toThrow('storage_unavailable');
  expect(() => f.journal.prepare('other', command, 1200)).toThrow('journal_not_open');
});

test('missing storage cannot open a handle or authorize preparing a request', () => {
  const journal = new AdministrationSessionJournal(undefined);
  expect(() => journal.open(context, 1000)).toThrow(JournalStorageError);
  expect(() => journal.prepare('key', command, 1000)).toThrow('journal_not_open');
});

test.each([undefined, 4, {}])('malformed provider return case %# fails without writing', raw => {
  const f = fixture(); f.storage.getItem.mockReturnValueOnce(raw as never);
  expect(() => f.journal.open(context, 1000)).toThrow('storage_unavailable');
  expect(f.storage.setItem).not.toHaveBeenCalled();
});

test.each(['not JSON', '{}', '{"version":1,"version":1}', ' '.repeat(65536)])(
  'malformed/noncanonical input case %# is preserved for explicit recovery', raw => {
    const f = fixture(); f.values.set(ADMINISTRATION_JOURNAL_KEY, raw);
    expect(() => f.journal.open(context, 1000)).toThrow('invalid_journal');
    expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(raw);
    expect(f.storage.setItem).not.toHaveBeenCalled();
  });

test.each([' '.repeat(65537), '"' + 'é'.repeat(40000) + '"'])(
  'byte bound case %# is checked before decoding or altering stored work', raw => {
    const f = fixture(); f.values.set(ADMINISTRATION_JOURNAL_KEY, raw);
    expect(() => f.journal.open(context, 1000)).toThrow('journal_too_large');
    expect(f.storage.setItem).not.toHaveBeenCalled();
  });

test('unknown fields and numeric revision coercion are never accepted as stored intent', () => {
  for (const edit of [(raw: Record<string, unknown>) => {raw.csrf = 'secret';},
    (raw: Record<string, unknown>) => {((raw.records as {payload: Record<string, unknown>}[])[0].payload).expected_revision = 9007199254740992;}]) {
    const f = fixture(); f.journal.open(context, 1000); f.journal.prepare('key', command, 1000);
    const raw = JSON.parse(f.values.get(ADMINISTRATION_JOURNAL_KEY)!); edit(raw);
    const encoded = JSON.stringify(raw); f.values.set(ADMINISTRATION_JOURNAL_KEY, encoded);
    expect(() => f.journal.open(context, 1100)).toThrow('invalid_journal');
    expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(encoded);
  }
});

test('a competing storage write cannot be overwritten or used through a stale in-memory handle', () => {
  const f = fixture(); f.journal.open(context, 1000);
  f.values.set(ADMINISTRATION_JOURNAL_KEY, 'competing original');
  expect(() => f.journal.prepare('key', command, 1100)).toThrow('storage_changed');
  expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe('competing original');
  expect(() => f.journal.prepare('again', command, 1200)).toThrow('journal_not_open');
});

test('a write without matching readback is not treated as confirmed persistence', () => {
  const f = fixture(); f.storage.setItem.mockImplementationOnce(() => {});
  expect(() => f.journal.open(context, 1000)).toThrow('storage_unconfirmed');
  expect(() => f.journal.prepare('key', command, 1000)).toThrow('journal_not_open');
});

test('a lost persistence write after a server receipt preserves the old original and the caller receipt', () => {
  const f = fixture(); f.journal.open(context, 1000);
  const original = f.journal.prepare('key', command, 1000).records[0];
  const receipt = Object.freeze({stage: 'committed' as const, operationId: 'original-op'});
  f.storage.setItem.mockImplementationOnce(() => {throw new Error('storage full');});
  expect(() => f.journal.record('key', receipt, 1100)).toThrow('storage_unavailable');
  expect(receipt.operationId).toBe('original-op');
  expect(f.journal.open(context, 1200).records).toEqual([original]);
});

test('invalid context and backward time cannot alter storage; only expiry removes old unresolved work', () => {
  const f = fixture();
  expect(() => f.journal.open({...context, subject: 'wrong'}, 1000)).toThrow('invalid_journal');
  expect(f.storage.setItem).not.toHaveBeenCalled();
  f.journal.open(context, 1000); f.journal.prepare('key', command, 1000);
  const stored = f.values.get(ADMINISTRATION_JOURNAL_KEY);
  expect(() => f.journal.open(context, 999)).toThrow('invalid_journal_time');
  expect(f.values.get(ADMINISTRATION_JOURNAL_KEY)).toBe(stored);
  expect(f.journal.open(context, 3600999).records).toHaveLength(1);
  expect(f.journal.open(context, 3601000).records).toEqual([]);
  expect(f.values.get(ENTRY_JOURNAL_KEY)).toBe('entry original');
});

test('real isolated browser sessionStorage supports a cold administration journal without a network effect', () => {
  const journal = new AdministrationSessionJournal(sessionStorage);
  journal.open(context, 1000); journal.prepare('original', command, 1000); journal.detach();
  const next = new AdministrationSessionJournal(sessionStorage);
  expect(next.open(context, 1100).records[0].payload.expected_revision).toBe('9007199254740993');
  expect(() => next.forget('original', 1200)).toThrow('unresolved_request');
});
