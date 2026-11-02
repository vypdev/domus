/** Closed exact integer transport; no Number round-trip or dependency on raw JSON interpolation. */
import {aliasValue, preferenceValues, revisionValue} from '../domain/administration';
import type {Revision} from '../domain/administration';
import {administrationCommand} from '../domain/administration-commands';
import type {AdministrationCommand} from '../domain/administration-commands';
export {administrationJSON, responseRevision, responseInteger} from './json-values';

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
