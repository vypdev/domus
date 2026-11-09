/** Shared closed JSON/scalar boundary; original integer sources never round through Number. */
import {EntryReadError} from '../application/ports';
import {revisionValue} from '../domain/administration';
import type {Revision} from '../domain/administration';

export type Fields = Record<string, unknown>;
export function invalid(): never {throw new EntryReadError('invalid_response');}
export function check(condition: unknown): asserts condition {if (!condition) invalid();}
export function fields(value: unknown, required: readonly string[], optional: readonly string[]): Fields {
  check(typeof value === 'object' && value !== null && !Array.isArray(value));
  check(required.every(key => Object.hasOwn(value, key))
    && Object.keys(value).every(key => required.includes(key) || optional.includes(key)));
  return value as Fields;
}
export function text(value: unknown, maximum: number): string {
  check(typeof value === 'string' && value.length > 0 && Array.from(value).length <= maximum
    && !/[\uD800-\uDFFF]/u.test(value)); return value;
}
export function integer(value: unknown, minimum: number): number {
  return responseInteger(value, minimum);
}
export function boolean(value: unknown): boolean {check(typeof value === 'boolean'); return value;}
export function choice<T extends string>(value: unknown, options: readonly T[]): T {
  check(typeof value === 'string' && options.includes(value as T)); return value as T;
}
export function identifier(value: unknown): string {
  check(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/u.test(value)); return value;
}
/** Bounded wire JSON: duplicate decoded keys/deep containers/unsafe numeric lexemes fail before coercion. */
export function wireJSON(raw: string): unknown {
  const stack: (Set<string> | null)[] = [];
  try {
    let index = 0;
    while (index < raw.length) {
      const character = raw[index++];
      if (character === '{' || character === '[') {
        stack.push(character === '{' ? new Set<string>() : null); check(stack.length <= 16);
      } else if (character === '}' || character === ']') stack.pop();
      else if (character === '"') {
        const start = index - 1;
        while (index < raw.length) {
          const next = raw[index++];
          if (next === '\\') index++;
          else if (next === '"') break;
        }
        let following = index;
        while (/\s/u.test(raw[following] ?? '')) following++;
        if (raw[following] === ':') {
          const keys = stack[stack.length - 1], key: unknown = JSON.parse(raw.slice(start, index));
          check(keys instanceof Set && typeof key === 'string' && !keys.has(key)); keys.add(key);
        }
      } else if (character === '-' || (character >= '0' && character <= '9')) {
        const start = index - 1;
        while (index < raw.length && /[^\s{}\[\],:"]/u.test(raw[index])) index++;
        const token = raw.slice(start, index);
        check(/^-?(?:0|[1-9]\d*)$/u.test(token) && token !== '-0' && Number.isSafeInteger(Number(token)));
      }
    }
    return JSON.parse(raw);
  } catch {return invalid();}
}
class ExactInteger {
  constructor(readonly source: string) {Object.freeze(this);}
}
const MIN_INTEGER = -9_223_372_036_854_775_808n;
const MAX_INTEGER = 9_223_372_036_854_775_807n;
export const JSON_MAX_BYTES = 65_536;
export const ROSTER_MAX_BYTES = 1_048_576;

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

export function administrationJSON(raw: unknown, maximumBytes: 65536 | 1048576 = JSON_MAX_BYTES): unknown {
  try {
    check(maximumBytes === JSON_MAX_BYTES || maximumBytes === ROSTER_MAX_BYTES);
    check(typeof raw === 'string' && raw.length <= maximumBytes
      && new TextEncoder().encode(raw).byteLength <= maximumBytes);
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

export function responseInteger(value: unknown, minimum = 0): number {
  check(value instanceof ExactInteger);
  const integer = BigInt(value.source);
  check(integer >= BigInt(minimum) && integer <= BigInt(Number.MAX_SAFE_INTEGER));
  return Number(integer);
}
