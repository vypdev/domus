import {LitElement,css,html,nothing} from 'lit';
import {live} from 'lit/directives/live.js';
import {repeat} from 'lit/directives/repeat.js';
import type {PropertyValues} from 'lit';
import type {AdministrationView} from '../application/administration-controller';
import {MAX_MATERIALIZATION_HORIZON_DAYS, MIN_MATERIALIZATION_HORIZON_DAYS} from '../domain/administration';
import {administrationCommand,MEMBER_ROLES,MEMBER_STATUSES,MAPPING_MODES,ORDINARY_PERMISSIONS} from '../domain/administration-commands';
import type {AdministrationCommand,MemberRole,PermissionDecision,ProfileDecision} from '../domain/administration-commands';
import type {AdministrationAction,PublicPresentation,RosterMember} from '../domain/administration-views';
import {administrationMessage} from './administration-messages';
import {instant} from './messages';
import type {Language} from './messages';
import {styles} from './styles';

export type AdministrationIntent = Readonly<{type:'submit';command:AdministrationCommand}>
  | Readonly<{type:'recover'|'dismiss';key:string}> | Readonly<{type:'refresh'}>;
type Draft = {key:string;owner:string;action:AdministrationAction;memberId?:string;payload:Record<string,unknown>;first:string;
  clearAlias:boolean;editRole:MemberRole;activationRequired:boolean;approved:boolean;
  review:AdministrationCommand|null;error:string|null;sent:boolean};
type Option = Readonly<{value:string;label:string;disabled?:boolean}>;

/** Owned form rendering and draft editing only. Application controls describe availability; the server reauthorizes. */
export class DomusAdministration extends LitElement {
  static properties={view:{attribute:false},language:{attribute:false},pending:{attribute:false},retired:{attribute:false}};
  static styles=[styles,css`
    :host {min-height:0;background:transparent} h3{font-size:1rem;margin:0 0 12px} .people{list-style:none;padding:0}
    .people>li{border-top:1px solid var(--line);padding:20px 0;overflow-wrap:anywhere}.people>li:first-child{border-top:0}
    .rules{display:grid;gap:12px}.rule{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:12px;align-items:center}
    .field input[type=checkbox]{width:24px;height:24px} form,fieldset{min-width:0} fieldset{border:0;padding:0;margin:0}
    button:disabled{cursor:not-allowed}.actions{margin-bottom:8px}.source{color:var(--muted);font-size:.875rem}
    @media(max-width:480px){.rule{grid-template-columns:1fr;gap:4px}}
  `];
  declare view:AdministrationView|null;
  declare language:Language;
  declare pending:boolean;
  declare retired:boolean;
  private readonly drafts=new Map<string,Draft>();
  private owner:string|null=null;
  private focusAfter:string|null=null;
  constructor(){super();this.view=null;this.language='en';this.pending=false;this.retired=false;}
  private t(key:string):string{return administrationMessage(key,this.language);}
  private scope(view:AdministrationView|null):string|null {
    return view?.session&&view.capabilities!==null&&view.access?.state==='active'&&view.access.member!==null
      ?JSON.stringify([view.session.context.installationId,view.session.context.channel,view.session.context.subject,view.access.member.memberId,view.capabilities.householdId]):null;
  }
  private ready():AdministrationView|null {
    const view=this.view;
    return !this.retired&&!this.pending&&view?.phase==='ready'&&!view.busy&&this.scope(view)!==null?view:null;
  }
  protected willUpdate(_changed:PropertyValues<this>):void {
    const scope=this.scope(this.view);
    if(this.retired||(this.view!==null&&scope===null)||(scope!==null&&this.owner!==null&&scope!==this.owner))this.drafts.clear();
    if(this.retired)this.owner=null;else if(scope!==null)this.owner=scope;
  }
  protected updated():void {
    this.lang=this.language==='es'?'es':'en';
    const id=this.focusAfter;this.focusAfter=null;
    if(id!==null){
      const original=this.shadowRoot!.getElementById(id);
      const target=original===null||original.matches(':disabled')?this.shadowRoot!.getElementById('administration-refresh'):original;
      target?.focus();
    }
  }
  disconnectedCallback():void {super.disconnectedCallback();this.drafts.clear();this.owner=null;this.view=null;}
  private intent(detail:AdministrationIntent):void {
    this.dispatchEvent(new CustomEvent<AdministrationIntent>('domus-administration-intent',{detail:Object.freeze(detail),bubbles:true,composed:true}));
  }
  private ownPresentation(view:AdministrationView):PublicPresentation|null {
    return view.presentation??view.roster?.members.find(row=>row.member.memberId===view.access!.member!.memberId)?.presentation??null;
  }
  private ownName(view:AdministrationView):string {
    return view.roster?.members.find(row=>row.member.memberId===view.access!.member!.memberId)?.metadata.name
      ??view.directory?.profiles.find(profile=>profile.haUserId===view.session!.context.subject)?.name??this.t('unnamed');
  }
  private actionTitle(action:AdministrationAction):string {
    switch(action){
      case 'household.update':return this.t('household');case 'policy.update':return this.t('policy');
      case 'member.update':return this.t('manage');case 'member.presentation.update':return this.t('alias');
      case 'member.preferences.update':return this.t('preferences');
    }
  }
  // Rendering checks ready proof; event handlers validate the current draft before inspecting controls.
  private enabled(draft:Draft):boolean {
    const view=this.view!;
    switch(draft.action){
      case 'household.update':return view.controls.household;case 'policy.update':return view.controls.policy;
      case 'member.preferences.update':return view.controls.preferences;
      case 'member.update':return view.controls.memberIds.includes(draft.memberId!);
      case 'member.presentation.update':return draft.memberId===view.access!.member!.memberId
        ?view.controls.ownAlias:view.controls.aliasMemberIds.includes(draft.memberId!);
    }
  }
  private current(draft:Draft):boolean {
    return this.ready()!==null&&this.drafts.get(draft.key)===draft&&draft.owner===this.scope(this.view);
  }
  private open(action:AdministrationAction,memberId?:string):void {
    const view=this.ready();if(view===null)return;
    const owner=this.scope(view)!;
    let payload:Record<string,unknown>,clearAlias=false,activationRequired=false,first:string;
    switch(action){
      case 'household.update':{
        const home=view.household;if(home===null)return;
        payload={expected_revision:home.revision,name:home.name,time_zone:home.timeZone};
        if(home.materializationHorizonDays!==undefined)payload.materialization_horizon_days=home.materializationHorizonDays;
        first='name';break;
      }
      case 'member.preferences.update':{
        const value=view.preferences;if(value===null)return;
        payload={expected_revision:value.revision,locale:value.locale??'',routine_participation_summaries:value.routine_participation_summaries};first='locale';break;
      }
      case 'member.presentation.update':{
        const value=memberId===view.access!.member!.memberId?this.ownPresentation(view):view.roster?.members.find(row=>row.member.memberId===memberId)?.presentation;
        if(!value)return;
        payload={expected_revision:value.revision,alias:value.alias??''};clearAlias=value.alias===null;first='clear';break;
      }
      case 'member.update':{
        const value=view.roster?.members.find(row=>row.member.memberId===memberId)?.member;if(!value||value.exceptions===null)return;
        payload={expected_revision:value.revision,role:value.status==='pending'?'restricted':value.role,status:value.status,exceptions:[...value.exceptions]};
        activationRequired=value.status!=='active';first='role';break;
      }
      case 'policy.update':{
        const value=view.policy;if(value===null)return;
        payload={expected_revision:value.revision,mapping_mode:value.mappingMode,target_ha_user_id:value.targetHAUserId,adjustments:[...value.adjustments]};first='mapping_mode';break;
      }
    }
    const key=action+':'+(memberId??'own');
    const draft:Draft={key,owner,action,...memberId===undefined?{}:{memberId},payload,first,clearAlias,editRole:'adult',activationRequired,
      approved:false,review:null,error:null,sent:false};
    if(!this.enabled(draft))return;
    this.drafts.set(key,draft);this.focusAfter=this.fieldId(draft,first);this.requestUpdate();
  }
  private fieldId(draft:Draft,field:string):string{return 'draft-'+draft.key+'-'+field;}
  private change(draft:Draft,key:string,value:unknown):void {
    if(!this.current(draft)||!this.enabled(draft)||draft.sent)return;
    draft.payload={...draft.payload,[key]:value};draft.error=null;this.requestUpdate();
  }
  private check(draft:Draft,key:'clearAlias'|'approved',value:boolean):void {
    if(!this.current(draft)||!this.enabled(draft)||draft.sent)return;
    draft[key]=value;draft.error=null;this.requestUpdate();
  }
  private review(draft:Draft):void {
    if(!this.current(draft)||!this.enabled(draft)||draft.sent)return;
    if(draft.activationRequired&&draft.payload.status==='active'&&!draft.approved){draft.error='activationRequired';}
    else try {
      const payload={...draft.payload};
      if(draft.action==='household.update'&&Object.hasOwn(payload,'materialization_horizon_days'))
        payload.materialization_horizon_days=Number(payload.materialization_horizon_days);
      if(draft.action==='member.presentation.update')payload.alias=draft.clearAlias?null:payload.alias;
      if(draft.action==='member.preferences.update'&&payload.locale==='')payload.locale=null;
      if(draft.action==='policy.update'&&payload.mapping_mode==='all_ha_administrators')payload.target_ha_user_id=null;
      draft.review=administrationCommand({action:draft.action,payload,...draft.memberId===undefined?{}:{memberId:draft.memberId}});
      draft.error=null;
    } catch {draft.error='invalid';}
    this.focusAfter=this.fieldId(draft,draft.error===null?'review':draft.error==='activationRequired'?'approved':draft.first);this.requestUpdate();
  }
  private save(draft:Draft):void {
    if(!this.current(draft)||!this.enabled(draft)||draft.sent||draft.review===null)return;
    draft.sent=true;this.intent({type:'submit',command:draft.review});this.requestUpdate();
  }
  private close(draft:Draft):void {
    if(!this.current(draft))return;
    this.drafts.delete(draft.key);this.focusAfter='open-'+draft.key;this.requestUpdate();
  }
  private reset(draft:Draft):void {
    if(this.current(draft)&&this.enabled(draft))this.open(draft.action,draft.memberId);
  }
  private field(draft:Draft,key:string,label:string,disabled=false) {
    const id=this.fieldId(draft,key),horizon=key==='materialization_horizon_days';
    return html`<div class="field"><label for=${id}>${this.t(label)}</label><input id=${id} type=${horizon?'number':'text'}
      min=${horizon?MIN_MATERIALIZATION_HORIZON_DAYS:nothing} max=${horizon?MAX_MATERIALIZATION_HORIZON_DAYS:nothing} autocomplete="off"
      .value=${live(String(draft.payload[key]))} ?disabled=${disabled||!this.enabled(draft)||draft.sent}
      aria-invalid=${draft.error===null?'false':'true'} aria-describedby=${draft.error===null?nothing:this.fieldId(draft,'error')} @input=${(event:InputEvent)=>this.change(draft,key,(event.target as HTMLInputElement).value)}></div>`;
  }
  private select(draft:Draft,key:string,label:string,options:readonly Option[],disabled=false) {
    const id=this.fieldId(draft,key);
    return html`<div class="field"><label for=${id}>${this.t(label)}</label><select id=${id} .value=${live(String(draft.payload[key]??''))}
      ?disabled=${disabled||!this.enabled(draft)||draft.sent} aria-invalid=${draft.error===null?'false':'true'} aria-describedby=${draft.error===null?nothing:this.fieldId(draft,'error')}
      @change=${(event:Event)=>this.change(draft,key,(event.target as HTMLSelectElement).value)}>
      ${options.map(option=>html`<option value=${option.value} .selected=${option.value===String(draft.payload[key]??'')}
        ?disabled=${option.disabled===true}>${option.label}</option>`)}</select></div>`;
  }
  private checkbox(draft:Draft,key:'clearAlias'|'approved'|'routine_participation_summaries',label:string) {
    const id=this.fieldId(draft,key==='clearAlias'?'clear':key),value=key==='routine_participation_summaries'?draft.payload[key]===true:draft[key];
    return html`<div class="field"><label for=${id}>${this.t(label)}</label><input id=${id} type="checkbox" .checked=${value}
      aria-describedby=${draft.error===null?nothing:this.fieldId(draft,'error')}
      ?disabled=${!this.enabled(draft)||draft.sent} @change=${(event:Event)=>{
        const checked=(event.target as HTMLInputElement).checked;
        if(key==='routine_participation_summaries')this.change(draft,key,checked);else this.check(draft,key,checked);
      }}></div>`;
  }
  private ruleChange(draft:Draft,permission:string,value:string):void {
    if(!this.current(draft)||!this.enabled(draft)||draft.sent)return;
    if(!['inherit','allow','deny'].includes(value)){draft.error='invalid';this.requestUpdate();return;}
    const profile=draft.action==='policy.update',key=profile?'adjustments':'exceptions';
    const prior=draft.payload[key] as readonly (PermissionDecision|ProfileDecision)[];
    const rules=prior.filter(rule=>rule.permission!==permission||(profile&&(rule as ProfileDecision).role!==draft.editRole));
    if(value!=='inherit')rules.push(profile?{role:draft.editRole,permission,allow:value==='allow'}:{permission,allow:value==='allow'});
    this.change(draft,key,rules);
  }
  private rules(draft:Draft) {
    const profile=draft.action==='policy.update',rules=draft.payload[profile?'adjustments':'exceptions'] as readonly (PermissionDecision|ProfileDecision)[];
    return html`<fieldset><legend>${this.t('permissions')}</legend><p class="help">${this.t('protected')}</p><div class="rules">
      ${ORDINARY_PERMISSIONS.map(permission=>{
        const rule=rules.find(value=>value.permission===permission&&(!profile||(value as ProfileDecision).role===draft.editRole));
        const id=this.fieldId(draft,'rule-'+permission);
        return html`<div class="rule"><label for=${id}>${this.t('permission_'+permission)}</label><select id=${id}
          .value=${live(rule===undefined?'inherit':rule.allow?'allow':'deny')} aria-describedby=${draft.error===null?nothing:this.fieldId(draft,'error')} ?disabled=${!this.enabled(draft)||draft.sent}
          @change=${(event:Event)=>this.ruleChange(draft,permission,(event.target as HTMLSelectElement).value)}>
          <option value="inherit" .selected=${rule===undefined}>${this.t(profile?'builtIn':'inherit')}</option>
          <option value="allow" .selected=${rule?.allow===true}>${this.t('allow')}</option><option value="deny" .selected=${rule?.allow===false}>${this.t('deny')}</option>
        </select></div>`;
      })}</div></fieldset>`;
  }
  private fields(draft:Draft) {
    switch(draft.action){
      case 'household.update':return html`${this.field(draft,'name','name')}${this.field(draft,'time_zone','zone')}<p class="help">${this.t('zoneHelp')}</p>
        ${Object.hasOwn(draft.payload,'materialization_horizon_days')?this.field(draft,'materialization_horizon_days','materializationHorizon'):nothing}`;
      case 'member.presentation.update':return html`${this.checkbox(draft,'clearAlias','useHA')}${this.field(draft,'alias','alias',draft.clearAlias)}`;
      case 'member.preferences.update':return html`${this.select(draft,'locale','savedLanguage',[
        {value:'',label:this.t('browserLanguage')},{value:'en',label:this.t('english')},{value:'es',label:this.t('spanish')}])}
        ${this.checkbox(draft,'routine_participation_summaries','summaries')}<p class="help">${this.t('delivery')}</p>`;
      case 'member.update':return html`${this.select(draft,'role','memberRole',MEMBER_ROLES.map(value=>({value,label:this.t('role_'+value)})))}
        ${this.select(draft,'status','status',MEMBER_STATUSES.map(value=>({value,label:this.t('status_'+value)})))}
        ${draft.activationRequired&&draft.payload.status==='active'?this.checkbox(draft,'approved','activation'):nothing}${this.rules(draft)}`;
      case 'policy.update':{
        const view=this.ready()!,directory=view.directory;
        const targets=directory?.state==='available'?directory.profiles.filter(profile=>profile.haUserId===view.session!.context.subject
          ||view.roster?.members.some(row=>row.member.status==='active'&&row.member.haUserId===profile.haUserId)):[];
        const available=targets.length>0;
        const options=MAPPING_MODES.map(value=>({value,label:this.t('mapping_'+value),disabled:value!=='all_ha_administrators'&&!available&&value!==draft.payload.mapping_mode}));
        const targetOptions:Option[]=[{value:'',label:this.t('chooseTarget')},...targets.map(profile=>({value:profile.haUserId,
          label:(profile.name??this.t('unnamed'))+' · '+profile.haUserId.slice(-6)}))];
        const saved=draft.payload.target_ha_user_id;
        if(typeof saved==='string'&&saved!==''&&!targets.some(profile=>profile.haUserId===saved))
          targetOptions.push({value:saved,label:this.t('savedTarget')+' · '+saved.slice(-6),disabled:true});
        const id=this.fieldId(draft,'editRole');
        return html`${this.select(draft,'mapping_mode','mapping',options)}<p class="help">${this.t('mappingHelp')}</p>
          ${draft.payload.mapping_mode!=='all_ha_administrators'?this.select(draft,'target_ha_user_id','target',targetOptions,!available):nothing}
          ${!available?html`<p class="note">${this.t('directoryUnavailable')}</p>`:nothing}
          <div class="field"><label for=${id}>${this.t('editRole')}</label><select id=${id} .value=${draft.editRole} aria-describedby=${draft.error===null?nothing:this.fieldId(draft,'error')} ?disabled=${!this.enabled(draft)||draft.sent}
            @change=${(event:Event)=>{
              if(!this.current(draft)||!this.enabled(draft)||draft.sent)return;
              const value=(event.target as HTMLSelectElement).value;
              if(MEMBER_ROLES.includes(value as MemberRole))draft.editRole=value as MemberRole;else draft.error='invalid';this.requestUpdate();
            }}>${MEMBER_ROLES.map(role=>html`<option value=${role} .selected=${draft.editRole===role}>${this.t('role_'+role)}</option>`)}</select></div>${this.rules(draft)}`;
      }
    }
  }
  private ruleSummary(rules:readonly PermissionDecision[]|readonly ProfileDecision[]) {
    return rules.length?html`<ul>${rules.map(rule=>html`<li>${'role'in rule?this.t('role_'+rule.role)+' · ':nothing}${this.t('permission_'+rule.permission)}: ${this.t(rule.allow?'allow':'deny')}</li>`)}</ul>`
      :html`<p class="help">${this.t('currentRules')}</p>`;
  }
  private summary(command:AdministrationCommand) {
    switch(command.action){
      case 'household.update':return html`<dl><dt>${this.t('name')}</dt><dd>${command.payload.name}</dd><dt>${this.t('zone')}</dt><dd>${command.payload.time_zone}</dd>
        ${command.payload.materialization_horizon_days===undefined?nothing:html`<dt>${this.t('materializationHorizon')}</dt><dd>${command.payload.materialization_horizon_days}</dd>`}</dl>`;
      case 'member.presentation.update':return html`<p>${this.t('alias')}: ${command.payload.alias??this.t('useHA')}</p>`;
      case 'member.preferences.update':return html`<p>${this.t('savedLanguage')}: ${this.t(command.payload.locale==='en'?'english':command.payload.locale==='es'?'spanish':'browserLanguage')}</p>
        <p>${this.t('summaries')}: ${this.t(command.payload.routine_participation_summaries?'allow':'deny')}</p><p class="help">${this.t('delivery')}</p>`;
      case 'member.update':return html`<p>${this.t('memberRole')}: ${this.t('role_'+command.payload.role)}</p><p>${this.t('status')}: ${this.t('status_'+command.payload.status)}</p>${this.ruleSummary(command.payload.exceptions)}`;
      case 'policy.update':return html`<p>${this.t('mapping')}: ${this.t('mapping_'+command.payload.mapping_mode)}</p>
        ${command.payload.target_ha_user_id===null?nothing:html`<p>${this.t('target')}: <code>…${command.payload.target_ha_user_id.slice(-6)}</code></p>`}${this.ruleSummary(command.payload.adjustments)}`;
    }
  }
  private readable(draft:Draft,view:AdministrationView):boolean {
    switch(draft.action){
      case 'household.update':return view.household!==null;
      case 'policy.update':return view.policy!==null;
      case 'member.preferences.update':return view.preferences!==null;
      case 'member.presentation.update':return draft.memberId===view.access!.member!.memberId
        ?this.ownPresentation(view)!==null:view.roster?.members.some(row=>row.member.memberId===draft.memberId)===true;
      case 'member.update':return view.roster?.members.some(row=>row.member.memberId===draft.memberId&&row.member.exceptions!==null)===true;
    }
  }
  private editor(draft:Draft,view:AdministrationView) {
    if(!this.readable(draft,view))return html`<section class="card" role="region" aria-label=${this.actionTitle(draft.action)}>
      <h3>${this.actionTitle(draft.action)}</h3><p class="note" role="status">${this.t('hiddenDraft')}</p>
      <button type="button" @click=${()=>this.close(draft)}>${this.t('close')}</button></section>`;
    const enabled=this.enabled(draft);
    const row=view.roster?.members.find(row=>row.member.memberId===draft.memberId);
    const target=draft.memberId===undefined?null:row?this.display(row):this.ownPresentation(view)!.alias??this.ownName(view);
    return html`<section class="card" role="region" aria-label=${this.actionTitle(draft.action)}><h3>${this.actionTitle(draft.action)}</h3>
      ${target===null?nothing:html`<p>${this.t('participant')}: <strong>${target}</strong></p>
        <p class="help">${this.t('memberReference')}: <code>${draft.memberId}</code></p>`}
      <p class="help">${this.t('revision')}: ${String(draft.payload.expected_revision)}</p>
      ${draft.error===null?nothing:html`<p id=${this.fieldId(draft,'error')} tabindex="-1" role="alert" class="error">${this.t(draft.error)}</p>`}
      ${!enabled?html`<p class="note">${this.t('locked')}</p>`:nothing}
      ${draft.review===null?html`<form novalidate @submit=${(event:SubmitEvent)=>{event.preventDefault();this.review(draft);}}>
        ${this.fields(draft)}<div class="actions"><button type="submit" class="primary" ?disabled=${!enabled||draft.sent}>${this.t('review')}</button>
          <button type="button" @click=${()=>this.close(draft)}>${this.t('cancel')}</button></div></form>`
        :html`<h4 id=${this.fieldId(draft,'review')} tabindex="-1">${this.t('reviewTitle')}</h4>${this.summary(draft.review)}
          ${draft.sent?html`<p role="status">${this.t('submitted')}</p>`:nothing}<div class="actions">
          <button type="button" class="primary" ?disabled=${!enabled||draft.sent} @click=${()=>this.save(draft)}>${this.t('save')}</button>
          <button type="button" ?disabled=${draft.sent} @click=${()=>{if(this.current(draft)){draft.review=null;draft.error=null;this.focusAfter=this.fieldId(draft,draft.first);this.requestUpdate();}}}>${this.t('back')}</button>
          <button type="button" @click=${()=>this.close(draft)}>${this.t('close')}</button></div>`}
      <button type="button" ?disabled=${!enabled} @click=${()=>this.reset(draft)}>${this.t('reset')}</button></section>`;
  }
  private openButton(label:string,action:AdministrationAction,enabled:boolean,memberId?:string,display?:string) {
    return html`<button id=${'open-'+action+':'+(memberId??'own')} type="button" ?disabled=${!enabled}
      aria-label=${display===undefined?this.t(label):this.t(label)+': '+display} @click=${()=>this.open(action,memberId)}>${this.t(label)}</button>`;
  }
  private display(row:RosterMember):string{return row.presentation.alias??row.metadata.name??this.t('unnamed');}
  private participants(view:AdministrationView) {
    const roster=view.roster;
    return html`<section class="card" role="region" aria-label=${this.t('participants')}><h3>${this.t('participants')}</h3>
      ${roster===null?html`<p>${this.t('unavailable')}</p>`:html`<ul class="people">${repeat(roster.members,row=>row.member.memberId,row=>html`<li>
        <strong>${this.display(row)}</strong><p class="source">${this.t('haName')}: ${row.metadata.name??this.t('metadata_'+row.metadata.state)}</p>
        <p>${this.t('storedProfile')}: ${this.t('role_'+row.member.role)} · ${this.t('status_'+row.member.status)}</p>
        <p class="help">${this.t('avatar')}</p><div class="actions">
          ${this.openButton('manage','member.update',view.controls.memberIds.includes(row.member.memberId),row.member.memberId,this.display(row))}
          ${row.member.memberId===view.access!.member!.memberId?nothing:this.openButton('otherAlias','member.presentation.update',view.controls.aliasMemberIds.includes(row.member.memberId),row.member.memberId,this.display(row))}
        </div></li>`)}</ul>`}</section>`;
  }
  private outcome(view:AdministrationView) {
    const result=view.outcome;if(result===null)return nothing;
    const kind=result.kind==='receipt'?result.stage:result.kind;
    return html`<section class="note" role="status"><h3>${this.t(kind)}</h3><p>${this.t(kind+'Body')}</p>
      ${result.kind==='receipt'?html`<p>${this.t('operation')}: <code>${result.operationId}</code></p>`:nothing}
      ${result.kind==='rejected'?html`<p>${this.t('notice_'+result.reason)}</p>${result.correlationId===null?nothing:html`<p>${this.t('correlation')}: <code>${result.correlationId}</code></p>`}`:nothing}</section>`;
  }
  private requests(view:AdministrationView) {
    const records=view.journal?.records;if(!records?.length)return nothing;
    return html`<section class="card" role="region" aria-label=${this.t('requests')}><h3>${this.t('requests')}</h3><p class="help">${this.t('requestHelp')}</p>
      <ul class="requests">${records.map(record=>html`<li><strong>${this.actionTitle(record.action)}</strong><p>${this.t('stage_'+record.stage)}</p>
        <p class="help">${this.t('deadline')}: ${instant(record.expiresAt,this.language)}</p>
        ${record.operationId===null?nothing:html`<p>${this.t('operation')}: <code>${record.operationId}</code></p>`}
        <div class="actions"><button type="button" ?disabled=${!view.controls.recoverableKeys.includes(record.key)} @click=${()=>this.original('recover',record.key)}>${this.t('check')}</button>
          <button type="button" ?disabled=${!view.controls.dismissibleKeys.includes(record.key)} @click=${()=>this.original('dismiss',record.key)}>${this.t('dismiss')}</button></div></li>`)}</ul></section>`;
  }
  private original(type:'recover'|'dismiss',key:string):void {
    const view=this.ready();if(view===null)return;
    if((type==='recover'?view.controls.recoverableKeys:view.controls.dismissibleKeys).includes(key))this.intent({type,key});
  }
  protected render() {
    const view=this.ready();
    if(view===null){
      if(this.pending||this.view?.busy||this.view?.phase==='loading')return html`<section class="note" role="status" aria-busy="true"><h2>${this.t('checking')}</h2><p>${this.t('checkingBody')}</p></section>`;
      if(this.view===null||this.retired)return nothing;
      return html`<section class="note" role="status"><h2>${this.t('title')}</h2><p>${this.t('notice_'+(this.view.notice??'unavailable'))}</p>
        <button id="administration-refresh" type="button" @click=${()=>this.intent({type:'refresh'})}>${this.t('refresh')}</button></section>`;
    }
    const person=view.access!.member!,own=this.ownPresentation(view);
    const haName=this.ownName(view);
    return html`<section role="region" aria-label=${this.t('title')}><h2>${this.t('title')}</h2>
      ${view.notice===null?nothing:html`<p class="note" role="status">${this.t('notice_'+view.notice)}</p>`}${this.outcome(view)}
      <section class="card"><h3>${this.t('ownProfile')}</h3><p><strong>${own?.alias??haName}</strong></p><p class="source">${this.t('haName')}: ${haName}</p>
        <p>${this.t('storedProfile')}: ${this.t('role_'+person.role)}</p><p>${this.t('effectiveProfile')}: ${this.t('role_'+view.access!.effectiveRole)}</p>
        <p>${this.t('status')}: ${this.t('status_'+person.status)}</p><p class="help">${this.t('avatar')}</p>
        ${this.openButton('editAlias','member.presentation.update',view.controls.ownAlias,person.memberId)}
        ${this.openButton('editPreferences','member.preferences.update',view.controls.preferences)}</section>
      ${this.participants(view)}<section class="card"><h3>${this.t('household')}</h3>${this.openButton('editHousehold','household.update',view.controls.household)}</section>
      <section class="card"><h3>${this.t('policy')}</h3><p class="help">${this.t('protected')}</p>${this.openButton('editPolicy','policy.update',view.controls.policy)}</section>
      ${[...this.drafts.values()].map(draft=>this.editor(draft,view))}${this.requests(view)}
      <button id="administration-refresh" type="button" @click=${()=>this.intent({type:'refresh'})}>${this.t('refresh')}</button></section>`;
  }
}
customElements.define('domus-administration',DomusAdministration);
declare global {interface HTMLElementTagNameMap {'domus-administration':DomusAdministration;}}
