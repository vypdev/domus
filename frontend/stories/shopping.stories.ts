import {html} from 'lit';
import type {Meta, StoryObj} from '@storybook/web-components-vite';
import type {EntryView} from '../src/application/entry-controller';
import type {InventoryState} from '../src/application/inventory-controller';
import type {TaskView} from '../src/application/task-controller';
import type {ShoppingItem, ShoppingSource} from '../src/domain/inventory';
import {entryDecision} from '../src/domain/entry';
import {revisionValue} from '../src/domain/administration';
import type {Language} from '../src/presentation/messages';
import '../src/presentation/domus-app';

type Example = 'default' | 'reader' | 'read-only' | 'uncertain' | 'rejected' | 'long-note' | 'empty';
type Arguments = {example:Example; language:Language; deployment:'native'|'standalone'};
const time=1_800_000_000_000, revision=revisionValue('1');
const context={installationId:'01234567-89ab-cdef-0123-456789abcdef',channel:'edge' as const,subject:'a'.repeat(32)};
const author={memberId:'fictional-requester',authorAlias:'Sam',createdAt:String(time-60000)};
const tea:ShoppingItem={productId:'fictional-tea',extraId:null,name:'Fictional tea',unit:'piece',
  pantry:'2',tasks:'0',manual:'2',total:'4',attribution:null,annotation:null};
const baseSource={lineId:null,reserved:'0',stock:'0',incoming:'0',quantity:'1',toBuy:'1'};
const sources:readonly ShoppingSource[]=[
  {...baseSource,id:'pantry:fictional-tea',kind:'pantry',originId:'fictional-tea',name:'Fictional tea',
    quantity:'2',toBuy:'2',attribution:null,annotation:null},
  {...baseSource,id:'extra:fictional-a',kind:'extra',originId:'fictional-a',name:'Fictional tea',attribution:author,
    annotation:{note:'Breakfast tea\nLoose leaves 😀',priority:'high'}},
  {...baseSource,id:'extra:fictional-b',kind:'extra',originId:'fictional-b',name:'Fictional tea',attribution:{...author,authorAlias:'Alex'},
    annotation:{note:'Keep this separate from the breakfast request.',priority:'low'}},
];

function entry(args:Arguments):EntryView {
  const session={context,deployment:args.deployment,access:args.example==='read-only'?'read_only' as const:'full' as const,
    serverTime:time,expiresAt:time+900000,householdApiAvailable:true};
  const authorization={state:'active' as const,setupAllowed:false,enrollmentAllowed:false,permissions:['household.read']};
  return{phase:'ready',busy:false,session,authorization,decision:entryDecision(args.deployment,session,authorization,time),
    household:{householdId:'fictional-home',name:'Maple House',timeZone:'Europe/Madrid',revision},
    journal:null,outcome:null,notice:null,fields:[],cleanup:null};
}

function inventory(args:Arguments):InventoryState {
  const note=args.example==='long-note'?'😀'.repeat(500)+'\n'+'😀'.repeat(499):'Untracked request\nKeep the printed label: <b>Tea</b>';
  const free:ShoppingItem={productId:null,extraId:'fictional-free',name:'Fictional fruit',unit:'piece',
    pantry:'0',tasks:'0',manual:'1',total:'1',attribution:author,annotation:{note,priority:'urgent'}};
  return{scope:{key:'fictional-shopping-scope',context,readOnly:args.example==='read-only'},
    report:{mayManage:false,mayShop:false,mayRequest:args.example!=='reader',cursor:null,locations:[],products:[
      {id:'fictional-tea',referenceId:'fictional-tea-reference',name:'Fictional tea',unit:'piece',
        recorded:'1',reserved:'0',available:'1',outstandingPurchase:'0',shoppingNeeded:'2',
        replenishment:{sourceId:'fictional-tea',minimum:'2',target:'3',revision,needed:'2'}},
    ]},history:null,busy:false,pending:args.example==='uncertain',notice:args.example==='uncertain'?'uncertain':null,
    result:args.example==='rejected'?{kind:'rejected',reason:'permission_denied',
      command:{action:'shopping.add-extra',product_id:null,name:'Fictional fruit',quantity:'1',note:'Keep my draft',priority:'high'}}:null,
    shoppingList:{items:args.example==='empty'?[]:[tea,free],cursor:null},
    shoppingSources:args.example==='empty'?null:{item:tea,items:sources,cursor:null}};
}

const meta:Meta<Arguments>={title:'Domus/Manual shopping annotations',args:{example:'default',language:'en',deployment:'native'},
  argTypes:{example:{control:false},language:{control:'inline-radio',options:['en','es']},
    deployment:{control:'inline-radio',options:['native','standalone']}},
  render:args=>{
    const view=entry(args);
    const tasks:TaskView={phase:'ready',busy:false,session:view.session,access:{householdId:'fictional-home',
      memberId:'fictional-requester',canCreate:false,canReviewSchedule:false},scopeKey:'fictional-shopping-workspace',
      readOnly:args.example==='read-only',page:{items:[],nextCursor:null},detail:null,materialHistory:null,records:[],outcome:null,notice:null};
    return html`<p style="margin:0;padding:8px 20px;background:#fff3cd;color:#523e09;font:14px system-ui">
      Fictional shopping state. No server is connected; actions emit intents only.</p>
      <domus-app .view=${view} .tasks=${tasks} .inventory=${inventory(args)} .language=${args.language}
        .deployment=${args.deployment} .workspaceDestination=${'inventory'}></domus-app>`;
  }};
export default meta;
type Story=StoryObj<Arguments>;
export const Default:Story={};
export const Reader:Story={args:{example:'reader'}};
export const ReadOnly:Story={args:{example:'read-only'}};
export const Uncertain:Story={args:{example:'uncertain'}};
export const Rejected:Story={args:{example:'rejected'}};
export const LongNote:Story={args:{example:'long-note'}};
export const Empty:Story={args:{example:'empty'}};
export const Spanish:Story={args:{language:'es'}};
