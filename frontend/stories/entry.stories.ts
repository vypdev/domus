import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {EntryView} from '../src/application/entry-controller';
import {entryDecision} from '../src/domain/entry';
import type {MembershipState} from '../src/domain/entry';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-app';

type Example = 'loading' | MembershipState | 'denied' | 'unavailable' | 'grace' | 'invalid' | 'uncertain' | 'historical';
type Arguments = {example: Example; language: Language; deployment: 'native' | 'standalone'};
const time = 1_800_000_000_000;
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const,
  subject: 'a'.repeat(32)};
/** Fictional render data only. Stories do not connect to a server or simulate completed commands. */
function fixture(example: Example, deployment: Arguments['deployment']): EntryView | null {
  if (example === 'loading') return null;
  const state: MembershipState = ['grace', 'uncertain', 'historical'].includes(example) ? 'active'
    : example === 'denied' || example === 'invalid' || example === 'unavailable' ? 'unconfigured' : example as MembershipState;
  const session = {context, deployment, access: example === 'grace' ? 'read_only' as const : 'full' as const,
    serverTime: time, expiresAt: time + 900_000, householdApiAvailable: example !== 'unavailable'};
  const authorization = {state, setupAllowed: state === 'unconfigured' && example !== 'denied',
    enrollmentAllowed: state === 'not_enrolled', permissions: state === 'active' ? ['household.read', 'operations.read'] : []};
  const record = {key: 'fictional-original-request', action: 'setup' as const, payload: {name: 'Maple House',
    time_zone: 'Europe/Madrid', expected_revision: 0 as const, mapping_mode: 'all_ha_administrators' as const},
    createdAt: time, expiresAt: time + 3_600_000,
    stage: example === 'historical' ? 'historical' as const : 'uncertain' as const,
    operationId: example === 'historical' ? 'op_fictional' : null};
  return {phase: 'ready', busy: false, session, authorization,
    decision: entryDecision(deployment, session, authorization, time),
    household: state === 'active' ? {householdId: 'fictional-home', name: 'Maple House', timeZone: 'Europe/Madrid', revision: 1} : null,
    journal: example === 'grace' ? null : {version: 1, context, observedAt: time,
      records: example === 'uncertain' || example === 'historical' ? [record] : []},
    outcome: example === 'uncertain' ? {kind: 'uncertain'} : example === 'historical'
      ? {kind: 'receipt', stage: 'historical', operationId: 'op_fictional', archivedBy: 'restore_fictional', createdAt: time,
        result: {state: 'configured'}} : null,
    notice: example === 'unavailable' ? 'unavailable' : null,
    fields: example === 'invalid' ? ['name', 'time_zone'] : [], cleanup: null};
}
const meta: Meta<Arguments> = {
  title: 'Domus/Household entry',
  args: {example: 'unconfigured', language: 'en', deployment: 'native'},
  argTypes: {language: {control: 'inline-radio', options: ['en', 'es']},
    deployment: {control: 'inline-radio', options: ['native', 'standalone']}, example: {control: false}},
  render: args => html`<p style="margin:0;padding:8px 20px;background:#fff3cd;color:#523e09;font:14px system-ui">
    Fictional interface state. No server is connected; actions emit intents only.</p>
    <domus-app .view=${fixture(args.example, args.deployment)} .language=${args.language} .deployment=${args.deployment}></domus-app>`,
};
export default meta;
type Story = StoryObj<Arguments>;
export const Loading: Story = {args: {example: 'loading'}};
export const Setup: Story = {};
export const Joining: Story = {args: {example: 'not_enrolled'}};
export const Pending: Story = {args: {example: 'pending'}};
export const Active: Story = {args: {example: 'active'}};
export const Suspended: Story = {args: {example: 'suspended'}};
export const Archived: Story = {args: {example: 'archived'}};
export const Denied: Story = {args: {example: 'denied'}};
export const Unavailable: Story = {args: {example: 'unavailable'}};
export const ReadOnly: Story = {args: {example: 'grace'}};
export const Invalid: Story = {args: {example: 'invalid'}};
export const Uncertain: Story = {args: {example: 'uncertain'}};
export const Historical: Story = {args: {example: 'historical'}};
export const Spanish: Story = {args: {example: 'unconfigured', language: 'es'}};
