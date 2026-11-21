import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {DailyPolicy, DailyReview, DailyView, ReviewedDailyTime} from '../src/application/automation-daily';
import type {DailyHistoryView, ScheduledAutomationRun} from '../src/application/automation-daily-history';
import type {EntryView} from '../src/application/entry-controller';
import type {TaskView} from '../src/application/task-controller';
import {entryDecision} from '../src/domain/entry';
import {revisionValue} from '../src/domain/administration';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-app';

type Example = 'review' | 'enabled' | 'timing-changed' | 'timing-unavailable' | 'no-task-create' | 'uncertain' | 'history';
type Arguments = {example: Example; language: Language; deployment: 'native' | 'standalone'};
const one = revisionValue('1'), two = revisionValue('2');
const policy: DailyPolicy = {zone: 'Europe/Madrid', dataIdentity: 'tzdata:2026.2', repeatedTime: 'first_instant', revision: one};
const time = Date.parse('2026-11-22T06:31:00Z');

function upcoming(selected = policy, offsetSeconds = 3600): readonly ReviewedDailyTime[] {
  return [23, 24, 25, 26, 27].map(day => ({nominal: `2026-11-${day}T07:30:00`, resolvedLocal: `2026-11-${day}T07:30:00`,
    policy: selected, offsetSeconds, resolution: 'exact', zoneDigest: 'a'.repeat(64)}));
}

function review(example: Example): DailyReview {
  const enabled = example !== 'review' && example !== 'uncertain';
  const changed = example === 'timing-changed';
  const proposedPolicy = changed ? {...policy, zone: 'America/New_York', revision: two} : policy;
  const unavailable = example === 'timing-unavailable';
  return {ruleId: 'fictional-daily-rule', ruleRevision: one, title: 'Check household soap', requestedTime: '07:30',
    controlRevision: enabled ? two : '0', scheduleRevision: enabled ? two : '0', enabled,
    activeTrigger: enabled ? 'daily' : null, activeRevision: enabled ? one : null, activeTitle: enabled ? 'Check household soap' : null,
    conditionProducts: ['fictional-soap'], condition: {kind: 'stock_below_minimum', product_id: 'fictional-soap'},
    mayEnable: example !== 'no-task-create', approvedPolicy: enabled ? policy : null, proposedPolicy,
    approvedTimes: enabled && !unavailable ? upcoming() : null, approvedUnavailable: unavailable,
    proposedTimes: unavailable ? [] : upcoming(proposedPolicy, changed ? -18000 : 3600), proposedUnavailable: unavailable,
    policyChanged: changed, next: enabled ? upcoming()[0] : null, suppression: null};
}

function daily(example: Example): DailyView | null {
  if (example === 'history') return null;
  return {review: example === 'uncertain' ? null : review(example), confirmation: null, result: null, notice: example === 'uncertain' ? 'uncertain' : null,
    busy: false, pending: example === 'uncertain', readOnly: false, savedRevision: one};
}

function history(example: Example): DailyHistoryView | null {
  if (example !== 'history') return {phase: 'closed', items: [], hasOlder: false, timeZone: policy.zone};
  // Scheduler keys use the fictional entry scope, rule revision 1 and each nominal date.
  // Separate admitted dates preserve the endpoint's newest-first ordering.
  const samples = [
    ['2026-11-22', '10961688d93dbd9d761605773d54fd2ec49fecb9ae14347c6fe48332131940b7', 'queued', false],
    ['2026-11-21', '7964b746972b97e90bc0a4c4a812ec21d297c6d6ccdffeee25c0353ee4db5088', 'created', false],
    ['2026-11-20', '9c053f865c792bcfcbc2341af5ff7cf0a0186ac722ba25808ace9f5a66160a86', 'no_task', false],
    ['2026-11-19', '8b2b02ed37b18d153387a2c9eb8fe22f049bc8feb2a0073d79706981b3f4825c', 'cancelled', false],
    ['2026-11-18', '8d556b6addc1b699eeb76340a5fb228dc0efedf0ced503617e3346b1b79af9e9', 'denied', false],
    ['2026-11-17', '41fd93ba5d04dea04708f1d15b5620f18fe92155219439e1a3e533e0b7e5d199', 'queued', true],
  ] as const;
  const items: ScheduledAutomationRun[] = samples.map(([day, key, outcome, historical]) => {
    const local = day + 'T07:30:00', scheduledAt = Date.parse(day + 'T06:30:00Z');
    return {key, ruleRevision: one, controlRevision: two, requestedLocal: local, resolvedLocal: local,
      scheduledAt, timeZone: policy.zone, resolution: 'exact', admittedAt: scheduledAt + 200, outcome,
      finishedAt: outcome === 'queued' ? null : scheduledAt + 2200, historical,
      taskOccurrenceId: outcome === 'created' ? 'fictional-created-task' : null,
      operationId: (outcome === 'queued' ? 'fictional-admission-' : 'fictional-result-') + day};
  });
  return {phase: 'ready', items, hasOlder: true, timeZone: policy.zone};
}

function entry(deployment: Arguments['deployment']): EntryView {
  const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
  const session = {context, deployment, access: 'full' as const, serverTime: time, expiresAt: time + 900000, householdApiAvailable: true};
  const authorization = {state: 'active' as const, setupAllowed: false, enrollmentAllowed: false, permissions: ['household.read']};
  return {phase: 'ready', busy: false, session, authorization, decision: entryDecision(deployment, session, authorization, time),
    household: {householdId: 'fictional-home', name: 'Maple House', timeZone: policy.zone, revision: one},
    journal: null, outcome: null, notice: null, fields: [], cleanup: null};
}

function workspace(example: Example, deployment: Arguments['deployment']): TaskView {
  return {phase: 'ready', busy: false, session: entry(deployment).session,
    access: {householdId: 'fictional-home', memberId: 'fictional-member', canCreate: example !== 'no-task-create', canReviewSchedule: false},
    scopeKey: 'fictional-workspace', readOnly: false, page: {items: [], nextCursor: null}, detail: null,
    materialHistory: null, records: [], outcome: null, notice: null};
}

const meta: Meta<Arguments> = {
  title: 'Domus/Daily automations', args: {example: 'review', language: 'en', deployment: 'native'},
  argTypes: {example: {control: false}, language: {control: 'inline-radio', options: ['en', 'es']},
    deployment: {control: 'inline-radio', options: ['native', 'standalone']}},
  render: args => html`<p style="margin:0;padding:8px 20px;background:#fff3cd;color:#523e09;font:14px system-ui">
      Fictional daily automation state. No server is connected; actions emit intents only.</p>
    <domus-app .view=${entry(args.deployment)} .language=${args.language} .deployment=${args.deployment}
      .tasks=${workspace(args.example, args.deployment)} .workspaceDestination=${'household'}
      .automationDaily=${daily(args.example)} .automationDailyHistory=${history(args.example)}></domus-app>`,
};
export default meta;
type Story = StoryObj<Arguments>;
export const Review: Story = {};
export const Enabled: Story = {args: {example: 'enabled'}};
export const TimingChanged: Story = {args: {example: 'timing-changed'}};
export const TimingUnavailable: Story = {args: {example: 'timing-unavailable'}};
export const NoTaskCreate: Story = {args: {example: 'no-task-create'}};
export const Uncertain: Story = {args: {example: 'uncertain'}};
export const History: Story = {args: {example: 'history'}};
export const Spanish: Story = {args: {example: 'timing-changed', language: 'es'}};
