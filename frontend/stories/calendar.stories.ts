import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {CalendarView} from '../src/application/calendar-controller';
import type {CalendarEntry} from '../src/domain/calendar';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-calendar';

const day = '2026-11-01';
const task = {title: 'Check the kitchen filter', day, time: null, zone: null, nominal: null, resolved: null, verification: null};
const entries: readonly CalendarEntry[] = [
  {...task, id: 'planned:filter', kind: 'planned', time: '08:30', zone: 'Europe/Madrid'},
  {...task, id: 'due:filter', kind: 'due'},
  {...task, id: 'performed:filter', kind: 'performed', time: '09:15', zone: 'Europe/Madrid'},
  {...task, id: 'approval:filter', kind: 'approval', time: '10:45', zone: 'Europe/Madrid', verification: 'approved'},
  {...task, id: 'due:untrusted', kind: 'due', title: '<img src=x onerror=alert(1)>'},
];
const view: CalendarView = {status: 'ready', page: {entries, count: entries.length, occurrenceCount: entries.length, cursor: null, pending: true}};

type Arguments = {language: Language};
const meta: Meta<Arguments> = {
  title: 'Domus/Calendar',
  args: {language: 'en'},
  argTypes: {language: {control: 'inline-radio', options: ['en', 'es']}},
  render: ({language}) => html`
    <p>Fictional calendar entries. This example does not query a server.</p>
    <domus-calendar .view=${view} .language=${language} .today=${day} .scopeKey=${'fictional-calendar'}></domus-calendar>`,
};
export default meta;

type Story = StoryObj<Arguments>;
export const PendingProcessing: Story = {};
export const Spanish: Story = {args: {language: 'es'}};
