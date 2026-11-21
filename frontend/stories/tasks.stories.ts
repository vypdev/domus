import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {TaskView} from '../src/application/task-controller';
import {revisionValue} from '../src/domain/administration';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-tasks';
const context = {installationId: '01234567-89ab-cdef-0123-456789abcdef', channel: 'edge' as const, subject: 'a'.repeat(32)};
const revision = revisionValue('1');
type Example = 'loading' | 'empty' | 'available' | 'pending' | 'read_only' | 'materials';
type Arguments = {language: Language; example: Example};
function fixture(example: Example): TaskView | null {
  if (example === 'loading') return null;
  const materials = example === 'materials', completed = example === 'pending' || materials;
  const choice = {referenceId:'fictional-soap',name:'Fictional soap',unit:'millilitre' as const};
  const work = {occurrenceId: 'fictional-work', definitionId: 'fictional-definition', definitionRevision: revision, title: 'Clean the kitchen',
    description: 'Wipe the table and put away the dishes.', priority: 'normal' as const, revision, state: completed ? 'completed' as const : 'available' as const,
    assigneeIds: [], dueAt: null, currentCycleId: completed ? 'fictional-cycle' : null,
    allowedActions: materials ? ['reopen', 'materials.settle'] : example === 'pending' ? ['approve', 'reject', 'reopen'] : ['claim', 'complete'],
    cycle: completed ? {cycleId: 'fictional-cycle', verification: materials ? 'none' as const : 'pending' as const, performedAt: '1800000000000', performerIds: ['fictional-member']} : null,
    materials: materials ? [
      {lineId:'fictional-posted',label:'Fictional cloth',plannedQuantity:'2',precision:0,unitId:'piece',locationId:'pantry'},
      {lineId:'fictional-unused',label:'Fictional sponge',plannedQuantity:'1',precision:0,unitId:'piece',locationId:'pantry'},
      {lineId:'fictional-shortfall',label:'Fictional soap',plannedQuantity:'1.25',precision:6,unitId:'millilitre',locationId:'pantry'},
    ] : [],
    materialOutcomes: materials ? (['posted','not_used','pending_regularization'] as const).map((state,index)=>({
      intentId:'fictional-intent-'+index,cycleId:'fictional-cycle',lineId:['fictional-posted','fictional-unused','fictional-shortfall'][index],revision,
      submittedQuantity:['1','0','1.25'][index],quantity:['1','0','1.25'][index],state,pendingReason:index===2?'insufficient_stock':null,
      confirmedQuantity:index===0?'1':null,confirmedEffectRevision:index===0?revision:null,effectRevision:'1',
      movementId:index===0?'fictional-movement':null,postedAt:index===0?'1800000000000':null,
    })) : [],
    materialRecording: 'review_on_completion' as const, dependencyReviewRequired: false, pendingMaterials: materials};
  return {phase: 'ready', busy: false, session: {context, deployment: 'native', access: example === 'read_only' ? 'read_only' : 'full', serverTime: 1800000000000, expiresAt: 1800000900000, householdApiAvailable: true},
    access: {householdId: 'fictional-home', memberId: 'fictional-member', canCreate: true, canReviewSchedule: true, canLinkMaterials:materials}, scopeKey: 'fictional-verified-scope', readOnly: example === 'read_only',
    ...(materials ? {materialPlan:{open:true,busy:false,canLink:true,readOnly:false,
      rows:[{referenceId:choice.referenceId,input:'1.25',choice}],choices:[choice],cursor:null,notice:null}} : {}),
    page: {items: example === 'empty' ? [] : [work], nextCursor: null}, detail: example === 'empty' ? null : work, materialHistory:null, records: [], outcome: null, notice: null};
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
export const Materials: Story = {args: {example: 'materials'}};
