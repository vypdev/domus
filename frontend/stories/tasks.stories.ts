import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {TaskView} from '../src/application/task-controller';
import {revisionValue} from '../src/domain/administration';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-tasks';
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const revision = revisionValue('1');
type Example = 'loading' | 'empty' | 'available' | 'pending' | 'read_only';
type Arguments = {language: Language; example: Example};
function fixture(example: Example): TaskView | null {
  if (example === 'loading') return null;
  const work = {occurrenceId: 'fictional-work', definitionId: 'fictional-definition', definitionRevision: revision, title: 'Clean the kitchen',
    description: 'Wipe the table and put away the dishes.', priority: 'normal' as const, revision, state: example === 'pending' ? 'completed' as const : 'available' as const,
    assigneeIds: [], dueAt: null, currentCycleId: null, allowedActions: example === 'pending' ? ['approve', 'reject', 'reopen'] : ['claim', 'complete'],
    cycle: example === 'pending' ? {cycleId: 'fictional-cycle', verification: 'pending' as const, performedAt: '1800000000000', performerIds: ['fictional-member']} : null,
    materials: [], materialRecording: 'review_on_completion' as const, dependencyReviewRequired: false, pendingMaterials: false};
  return {phase: 'ready', busy: false, session: {context, deployment: 'native', access: example === 'read_only' ? 'read_only' : 'full', serverTime: 1800000000000, expiresAt: 1800000900000, householdApiAvailable: true},
    access: {householdId: 'fictional-home', memberId: 'fictional-member', canCreate: true}, scopeKey: 'fictional-verified-scope', readOnly: example === 'read_only',
    page: {items: example === 'empty' ? [] : [work], nextCursor: null}, detail: example === 'empty' ? null : work, records: [], outcome: null, notice: null};
}
const meta: Meta<Arguments> = {title: 'Domus/Tasks', args: {language: 'en', example: 'available'},
  argTypes: {language: {control: 'inline-radio', options: ['en', 'es']}, example: {control: false}},
  render: args => html`<p style="padding:8px 20px;background:#fff3cd;color:#523e09;font:14px system-ui">Fictional interface state. No server is connected; actions emit intents only.</p>
    <div style="max-width:960px;padding:24px;margin:auto"><domus-tasks .view=${fixture(args.example)} .language=${args.language}></domus-tasks></div>`};
export default meta;
type Story = StoryObj<Arguments>;
export const Available: Story = {};
export const Loading: Story = {args: {example: 'loading'}};
export const Empty: Story = {args: {example: 'empty'}};
export const PendingApproval: Story = {args: {example: 'pending'}};
export const ReadOnly: Story = {args: {example: 'read_only'}};
export const Spanish: Story = {args: {language: 'es'}};
