import {expect, test} from 'vitest';
import {administrationAllowed} from '../src/domain/administration-authorization';
import type {AdministrationAccess} from '../src/domain/administration-views';
import {administrationCommand} from '../src/domain/administration-commands';
import {revisionValue} from '../src/domain/administration';

const own = 'member-own';
const access: AdministrationAccess = {state: 'active', setupAllowed: false, enrollmentAllowed: false,
  permissions: ['preferences.write'], policyRevision: revisionValue('1'), effectiveRole: 'administrator',
  member: {memberId: own, role: 'administrator', status: 'active', revision: revisionValue('1'), haUserId: null, exceptions: null}};
const preferences = administrationCommand({action: 'member.preferences.update', payload: {expected_revision: '1', locale: 'es', routine_participation_summaries: true}});
const alias = (memberId: string) => administrationCommand({action: 'member.presentation.update', memberId, payload: {expected_revision: '1', alias: 'Name'}});

test.each(['unconfigured','not_enrolled','pending','suspended','archived'] as const)('HADW-04: granted strings and role labels cannot activate %s membership', state => {
  expect(administrationAllowed({...access, state}, preferences)).toBe(false);
});
test('HADW-02: a missing current membership does not grant owner preferences', () => {
  expect(administrationAllowed({...access, member: null}, preferences)).toBe(false);
});
test('HADW-01/02: public alias owner scope and explicit administrator permission remain separate', () => {
  expect(administrationAllowed(access, preferences)).toBe(true);
  expect(administrationAllowed(access, alias(own))).toBe(true);
  expect(administrationAllowed(access, alias('another'))).toBe(false);
  expect(administrationAllowed({...access, permissions: ['members.manage']}, alias('another'))).toBe(true);
  expect(administrationAllowed({...access, permissions: []}, alias(own))).toBe(false);
});
