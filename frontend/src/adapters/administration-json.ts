/** Closed exact integer transport; no Number round-trip or dependency on raw JSON interpolation. */
import {aliasValue, preferenceValues, revisionValue} from '../domain/administration';
import type {Revision} from '../domain/administration';
import {administrationCommand} from '../domain/administration-commands';
import type {AdministrationCommand} from '../domain/administration-commands';
import {check, invalid, wireJSON} from './http-values';

class ExactInteger {
  constructor(readonly source: string) {Object.freeze(this);}
}
const MIN_INTEGER = -9_223_372_036_854_775_808n;
const MAX_INTEGER = 9_223_372_036_854_775_807n;
const MAX_BYTES = 65_536;

function maskNumbers(raw: string): string {
  const parts: string[] = []; let index = 0;
  while (index < raw.length) {
    const start = index, character = raw[index++];
    if (character === '"') {
      while (index < raw.length) {
        const next = raw[index++];
        if (next === '\\') index++;
        else if (next === '"') break;
      }
    } else if (character === '-' || (character >= '0' && character <= '9')) {
      while (index < raw.length && /[^\s{}\[\],:"]/u.test(raw[index])) index++;
      const token = raw.slice(start, index);
      check(/^-?(?:0|[1-9]\d*)$/u.test(token) && token !== '-0'
        && BigInt(token) >= MIN_INTEGER && BigInt(token) <= MAX_INTEGER);
      parts.push('0'); continue;
    }
    parts.push(raw.slice(start, index));
  }
  return parts.join('');
}

export function administrationJSON(raw: unknown): unknown {
  try {
    check(typeof raw === 'string' && raw.length <= MAX_BYTES
      && new TextEncoder().encode(raw).byteLength <= MAX_BYTES);
    // Validate syntax, decoded-key uniqueness and nesting with the existing bounded reader.
    // Mask numeric tokens only for that preflight; the original lexical source remains untouched.
    wireJSON(maskNumbers(raw));
    return JSON.parse(raw, (_key, value: unknown, context?: {source?: string}): unknown => {
      if (typeof value !== 'number') return value;
      // Unsupported engines fail closed; a rounded Number is never accepted as original evidence.
      check(typeof context?.source === 'string');
      return new ExactInteger(context.source);
    });
  } catch {return invalid();}
}

export function responseRevision(value: unknown): Revision {
  check(value instanceof ExactInteger);
  try {return revisionValue(value.source);} catch {return invalid();}
}

export function responseInteger(value: unknown): number {
  check(value instanceof ExactInteger);
  const integer = BigInt(value.source);
  check(integer >= 0n && integer <= BigInt(Number.MAX_SAFE_INTEGER));
  return Number(integer);
}

export function aliasBody(expected: Revision, alias: unknown): string {
  return '{"expected_revision":' + revisionValue(expected)
    + ',"alias":' + JSON.stringify(aliasValue(alias)) + '}';
}

export function preferencesBody(expected: Revision, locale: unknown, summaries: unknown): string {
  const values = preferenceValues(locale, summaries);
  return '{"expected_revision":' + revisionValue(expected) + ',' + JSON.stringify(values).slice(1);
}

/** Encode an already chosen original intent without normalizing or selecting its HTTP target. */
export function administrationCommandBody(value: AdministrationCommand): string {
  const {expected_revision, ...fields} = administrationCommand(value).payload;
  return '{"expected_revision":' + expected_revision + ',' + JSON.stringify(fields).slice(1);
}
