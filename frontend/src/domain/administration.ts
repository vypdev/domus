/** Pure administration values never authenticate a person or grant a permission. */
declare const revisionBrand: unique symbol;
export type Revision = string & {readonly [revisionBrand]: true};
export type MemberLocale = 'en' | 'es' | null;
export interface OwnPreferenceValues {
  readonly locale: MemberLocale;
  readonly routine_participation_summaries: boolean;
}
export type AdministrationFault = 'invalid_revision' | 'revision_exhausted'
  | 'invalid_alias' | 'invalid_preferences' | 'invalid_command';
export class AdministrationError extends Error {
  constructor(readonly code: AdministrationFault) {
    super(code); this.name = 'AdministrationError';
  }
}

const MAX_REVISION = 9_223_372_036_854_775_807n;

/** Decimal text is the browser value, independently of the integer HTTP representation. */
export function revisionValue(value: unknown): Revision {
  if (typeof value !== 'string' || value.length === 0 || value.length > 19
      || value[0] === '0' || /[^0-9]/u.test(value) || BigInt(value) > MAX_REVISION)
    throw new AdministrationError('invalid_revision');
  return value as Revision;
}

export function nextRevision(value: Revision): Revision {
  const current = BigInt(revisionValue(value));
  if (current === MAX_REVISION) throw new AdministrationError('revision_exhausted');
  return revisionValue(String(current + 1n));
}

export function aliasValue(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || /[\p{Cc}\uD800-\uDFFF]/u.test(value))
    throw new AdministrationError('invalid_alias');
  // Python's accepted whitespace differs from String.trim() for U+FEFF. Cc was already rejected.
  const alias = value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '');
  if (alias.length === 0 || Array.from(alias).length > 80)
    throw new AdministrationError('invalid_alias');
  return alias;
}

export function preferenceValues(locale: unknown, summaries: unknown): Readonly<OwnPreferenceValues> {
  if ((locale !== null && locale !== 'en' && locale !== 'es') || typeof summaries !== 'boolean')
    throw new AdministrationError('invalid_preferences');
  return Object.freeze({locale, routine_participation_summaries: summaries});
}
