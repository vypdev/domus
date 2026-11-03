import {html} from 'lit';
import type {Meta,StoryObj} from '@storybook/web-components-vite';
import type {AdministrationView} from '../src/application/administration-controller';
import {revisionValue} from '../src/domain/administration';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-administration';

type Example='active'|'read-only'|'sources-unavailable'|'uncertain'|'historical';
type Arguments={example:Example;language:Language;deployment:'native'|'standalone'};
const time=1_800_000_000_000;
const context={installationId:'01234567-89ab-cdef-0123-456789abcdef',channel:'edge' as const,subject:'a'.repeat(32)};
/** Fictional view data only; actions emit intents and never manufacture a server result. */
function fixture(example:Example,deployment:Arguments['deployment']):AdministrationView {
  const readOnly=example==='read-only',unavailable=example==='sources-unavailable';
  const member={memberId:'fictional-owner',haUserId:context.subject,role:'adult' as const,status:'active' as const,revision:revisionValue('3'),exceptions:[]};
  const presentation={memberId:member.memberId,alias:null,revision:revisionValue('11')};
  const journaled=example==='uncertain'||example==='historical';
  const stage=example==='historical'?'historical' as const:'uncertain' as const;
  return {phase:'ready',busy:false,session:{context,deployment,access:readOnly?'read_only':'full',serverTime:time,expiresAt:time+900_000,householdApiAvailable:true},
    access:{state:'active',setupAllowed:false,enrollmentAllowed:false,member,effectiveRole:'administrator',policyRevision:revisionValue('5'),
      permissions:['household.read','household.manage','members.read','members.manage','policy.manage','preferences.read','preferences.write','operations.read']},
    capabilities:{contractVersion:2,householdId:'fictional-home',actions:['household.update','member.update','policy.update','member.presentation.update','member.preferences.update']},
    household:{householdId:'fictional-home',name:'Maple House',timeZone:'Europe/Madrid',revision:revisionValue('7')},
    policy:{householdId:'fictional-home',mappingMode:'all_ha_administrators',targetHAUserId:null,adjustments:[],revision:revisionValue('5')},
    directory:unavailable?{state:'denied',profiles:[]}:{state:'available',profiles:[{haUserId:context.subject,name:'Fictional owner'}]},
    roster:{directoryState:unavailable?'denied':'available',members:[{member,presentation,
      metadata:{state:unavailable?'denied':'available',name:unavailable?null:'Fictional owner',avatarState:'unavailable'}},
      {member:{...member,memberId:'fictional-pending',haUserId:'b'.repeat(32),role:'restricted',status:'pending'},
        presentation:{memberId:'fictional-pending',alias:null,revision:revisionValue('1')},
        metadata:{state:'available',name:'Fictional pending participant',avatarState:'unavailable'}}]},
    presentation,preferences:{memberId:member.memberId,locale:null,routine_participation_summaries:true,revision:revisionValue('13'),notificationDelivery:'unavailable'},
    errors:{},notice:readOnly?'read_only':null,
    journal:{context,observedAt:time,records:journaled?[{action:'member.preferences.update',payload:{expected_revision:revisionValue('12'),locale:null,routine_participation_summaries:true},
      context,key:'fictional-original',createdAt:time,expiresAt:time+3_600_000,stage,operationId:example==='historical'?'op_fictional':null}]:[]},
    outcome:example==='uncertain'?{kind:'uncertain'}:example==='historical'?{kind:'receipt',stage:'historical',action:'member.preferences.update',operationId:'op_fictional',
      archivedBy:'restore_fictional',createdAt:time,result:{memberId:member.memberId,locale:null,routine_participation_summaries:true,notificationDelivery:'unavailable',revision:revisionValue('13')},notificationDelivery:'unavailable',eventDelivery:'suppressed'}:null,
    controls:{household:!readOnly,policy:!readOnly,preferences:!readOnly&&example!=='uncertain',ownAlias:!readOnly,memberIds:readOnly?[]:['fictional-owner','fictional-pending'],
      aliasMemberIds:readOnly?[]:['fictional-pending'],recoverableKeys:journaled?['fictional-original']:[],dismissibleKeys:example==='historical'?['fictional-original']:[]}};
}
const meta:Meta<Arguments>={title:'Domus/Household administration',args:{example:'active',language:'en',deployment:'native'},
  argTypes:{language:{control:'inline-radio',options:['en','es']},deployment:{control:'inline-radio',options:['native','standalone']},example:{control:false}},
  render:args=>html`<p style="margin:0;padding:8px 20px;background:#fff3cd;color:#523e09;font:14px system-ui">
    Fictional administration state. No server is connected; actions emit intents only.</p>
    <domus-administration .view=${fixture(args.example,args.deployment)} .language=${args.language}></domus-administration>`};
export default meta;
type Story=StoryObj<Arguments>;
export const Active:Story={};
export const ReadOnly:Story={args:{example:'read-only'}};
export const SourcesUnavailable:Story={args:{example:'sources-unavailable'}};
export const Uncertain:Story={args:{example:'uncertain'}};
export const Historical:Story={args:{example:'historical'}};
