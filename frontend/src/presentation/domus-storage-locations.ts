import {LitElement, css, html, nothing} from 'lit';
import type {PropertyValues} from 'lit';
import {registerButton} from '@vypdev/ha-ui/button';
import {buttonState} from '@vypdev/ha-ui/button-contracts';
import {registerCard} from '@vypdev/ha-ui/card';
import {cardState} from '@vypdev/ha-ui/card-contracts';
import {registerField} from '@vypdev/ha-ui/field';
import type {FieldValueEvent} from '@vypdev/ha-ui/field';
import {textFieldState} from '@vypdev/ha-ui/field-contracts';
import type {InventoryState} from '../application/inventory-controller';
import type {Revision} from '../domain/administration';
import {locationName} from '../domain/inventory';
import type {InventoryCommand, StorageLocation} from '../domain/inventory';
import {inventoryMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import type {Language} from './messages';

type Action = 'rename' | 'archive' | 'restore';
interface Editor {readonly action: Action; readonly id: string; readonly revision: Revision; readonly reviewRequired: boolean;}
const TITLE = {rename:'reviewLocationRename', archive:'reviewLocationArchive', restore:'reviewLocationRestore'} as const;

/** Location drafts belong to this household and stay independent of other Inventory forms. */
export class DomusStorageLocations extends LitElement {
  static properties = {
    view:{attribute:false}, language:{attribute:false}, addDraft:{state:true}, addError:{state:true},
    renameDraft:{state:true}, renameError:{state:true}, editor:{state:true}, archivedOpen:{state:true},
  };
  static styles = css`
    :host {display:block;min-width:0}
    .location-content, form, li {display:grid;gap:8px;min-width:0}
    .location-content {gap:16px}
    h4,p {margin:0;overflow-wrap:anywhere} h4 {font-size:inherit}
    ul {list-style:none;padding:0;margin:0;display:grid;gap:12px}
    li + li, .location-review {border-block-start:1px solid var(--line);padding-block-start:12px}
    li {scroll-margin-block-start:68px;overflow-wrap:anywhere}
    .actions {display:flex;flex-wrap:wrap;gap:8px;min-width:0}
    .actions > span {min-width:0;max-width:100%}
    vyp-ha-button {min-width:0;max-width:100%}
    vyp-ha-field {min-width:0;--vyp-ha-danger:var(--warning);
      --vyp-ha-font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    summary {cursor:pointer;padding-block:8px;min-height:28px;overflow-wrap:anywhere}
    details > ul {margin-block-start:8px}
    :focus-visible {outline:3px solid var(--accent);outline-offset:3px}
  `;
  declare view: InventoryState | null;
  declare language: Language;
  private declare addDraft: string;
  private declare addError: InventoryMessage | null;
  private declare renameDraft: string;
  private declare renameError: InventoryMessage | null;
  private declare editor: Editor | null;
  private declare archivedOpen: boolean;
  private renameOwner: string | null = null;
  private addResetPending = false;
  private focusRequest: {selector: string; scope: string; location?: {id:string;revision?:Revision}} | null = null;

  constructor() {
    super(); this.view=null; this.language='en'; this.addDraft=''; this.addError=null;
    this.renameDraft=''; this.renameError=null; this.editor=null; this.archivedOpen=false;
  }

  private text(key: InventoryMessage): string {return inventoryMessage(key,this.language);}
  private blocked(): boolean {
    const view=this.view; return view===null || view.scope.readOnly || view.busy || view.pending;
  }
  private mayManage(): boolean {return this.view?.report?.mayManage===true && !this.view.scope.readOnly;}
  private selected(): StorageLocation | undefined {
    return this.view?.report?.locations.find(item=>item.id===this.editor?.id);
  }
  private allowed(action: Action, item: StorageLocation): boolean {return action==='restore' ? item.archived : !item.archived;}
  private queueFocus(selector: string, location?: {id:string;revision?:Revision}): void {
    this.focusRequest={selector,scope:this.view!.scope.key,location};
  }
  private rowSelector(id: string): string {return '[data-location-id="'+id+'"]';}

  protected willUpdate(changed: PropertyValues<this>): void {
    if(!changed.has('view'))return;
    const previous=changed.get('view'), current=this.view;
    if(previous?.scope.key!==current?.scope.key){
      this.addDraft='';this.addError=null;this.renameDraft='';this.renameError=null;
      this.renameOwner=null;this.editor=null;this.archivedOpen=false;this.focusRequest=null;
      this.addResetPending=false;
    }
    const result=current?.result;
    if(!result || result===previous?.result)return;
    if(result.kind==='rejected'){
      if(result.command.action==='inventory.add-location'){
        this.addError=result.reason;this.queueFocus('.location-add vyp-ha-field');
      }else if('location_id' in result.command && this.editor?.id===result.command.location_id
          && result.command.action==='inventory.'+this.editor.action+'-location'){
        this.renameError=result.reason;
        this.queueFocus(this.editor.action==='rename' ? '.location-review vyp-ha-field' : '.location-review h4');
      }
      return;
    }
    if(result.addedLocation && result.kind==='committed' && this.addDraft.trim()===result.addedLocation.name){
      this.addDraft='';this.addError=null;this.addResetPending=true;
      if(this.editor===null)this.queueFocus(this.rowSelector(result.addedLocation.id),result.addedLocation);
    }
    if(result.locationChanged){
      const {action,location}=result.locationChanged;
      if(this.editor?.id===location.id && action==='inventory.'+this.editor.action+'-location'){
        if(result.kind==='historical' || (this.editor.action==='rename' && this.renameDraft.trim()!==location.name)){
          this.editor={...this.editor,reviewRequired:true};
        }else{
          if(this.editor.action==='rename'){this.renameDraft='';this.renameOwner=null;}
          this.editor=null;this.renameError=null;this.queueFocus(this.rowSelector(location.id),location);
        }
      }else if(this.editor===null)this.queueFocus(this.rowSelector(location.id),result.kind==='committed'?location:{id:location.id});
    }
  }

  protected updated(): void {
    if(this.addResetPending){
      this.addResetPending=false;
      this.renderRoot.querySelector<HTMLFormElement>('.location-add')?.reset();
    }
    if(this.view?.busy || this.focusRequest===null)return;
    const expected=this.focusRequest.location;
    if(expected){
      const current=this.view?.report?.locations.find(item=>item.id===expected.id);
      // The command receipt can render before its subsequent catalog refresh.
      // Wait for that row/revision so archive focus follows it into the details.
      if(!current || (expected.revision!==undefined && BigInt(current.revision)<BigInt(expected.revision)))return;
    }
    const request=this.focusRequest;this.focusRequest=null;
    // A newly recreated card exposes its body after native slot distribution.
    // Focus after that render frame, while still checking the current scope.
    void this.updateComplete.then(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()))).then(()=>{
      if(this.view?.scope.key!==request.scope)return;
      const target=this.renderRoot.querySelector<HTMLElement>(request.selector);
      const details=target?.closest('details');
      if(details){this.archivedOpen=true;details.open=true;}
      target?.focus();
    });
  }

  private intent(command: InventoryCommand): void {
    this.dispatchEvent(new CustomEvent('domus-inventory-intent',{
      detail:{type:'submit',command},bubbles:true,composed:true,
    }));
  }
  private button(key: InventoryMessage, action: ()=>void, disabled: boolean, suffix='') {
    return html`<vyp-ha-button .state=${buttonState({label:this.text(key)+(suffix?' '+suffix:''),variant:'outlined'})}
      ?disabled=${disabled} @ha-press-request=${action}></vyp-ha-button>`;
  }
  private submit(key: InventoryMessage, disabled: boolean) {
    return html`<vyp-ha-button type="submit" .state=${buttonState({label:this.text(key),variant:'primary'})}
      ?disabled=${disabled}></vyp-ha-button>`;
  }
  private begin(action: Action, item: StorageLocation): void {
    if(this.blocked() || !this.mayManage() || !this.allowed(action,item))return;
    if(action==='rename' && this.renameOwner!==item.id){this.renameOwner=item.id;this.renameDraft=item.name;}
    this.editor={action,id:item.id,revision:item.revision,reviewRequired:false};this.renameError=null;
    this.queueFocus(action==='rename' ? '.location-review vyp-ha-field' : '.location-review h4');
  }
  private cancel(): void {
    if(this.blocked() || this.editor===null)return;
    const {id,action}=this.editor;
    if(action==='rename'){this.renameDraft='';this.renameOwner=null;}
    this.editor=null;this.renameError=null;
    this.queueFocus(this.rowSelector(id)+' [data-action="'+action+'"] vyp-ha-button');
  }
  private reviewCurrent(): void {
    const selected=this.selected();
    if(this.blocked() || !this.mayManage() || !selected || this.editor===null || !this.allowed(this.editor.action,selected))return;
    this.editor={...this.editor,revision:selected.revision,reviewRequired:false};this.renameError=null;
    this.queueFocus(this.editor.action==='rename' ? '.location-review vyp-ha-field' : '.location-review h4');
  }
  private add(event: SubmitEvent): void {
    event.preventDefault();if(this.blocked() || !this.mayManage())return;
    let name:string;
    try{name=locationName(this.addDraft.trim());}
    catch{this.addError='invalid_inventory_location_name';this.renderRoot.querySelector<HTMLElement>('.location-add vyp-ha-field')?.focus();return;}
    this.intent({action:'inventory.add-location',name});
  }
  private change(event: SubmitEvent): void {
    event.preventDefault();const editor=this.editor,current=this.selected();
    if(this.blocked() || !this.mayManage() || !editor || !current || editor.reviewRequired
        || current.revision!==editor.revision || !this.allowed(editor.action,current))return;
    if(editor.action==='rename'){
      let name:string;
      try{name=locationName(this.renameDraft.trim());}
      catch{this.renameError='invalid_inventory_location_name';this.renderRoot.querySelector<HTMLElement>('.location-review vyp-ha-field')?.focus();return;}
      if(name===current.name)return;
      this.intent({action:'inventory.rename-location',location_id:editor.id,name,expected_revision:editor.revision});
    }else if(editor.action==='archive'){
      if(current.archiveBlockedReason!==null)return;
      this.intent({action:'inventory.archive-location',location_id:editor.id,expected_revision:editor.revision});
    }else this.intent({action:'inventory.restore-location',location_id:editor.id,expected_revision:editor.revision});
  }
  private row(item: StorageLocation, manage: boolean, blocked: boolean) {
    return html`<li tabindex="-1" data-location-id=${item.id}>
      <p><strong>${item.name}</strong>${item.archived ? html` · ${this.text('archivedLocation')}` : nothing}</p>
      ${manage ? html`<div class="actions">
        ${item.archived ? html`<span data-action="restore">${this.button('restoreLocation',()=>this.begin('restore',item),blocked,item.name)}</span>`
          : html`<span data-action="rename">${this.button('renameLocation',()=>this.begin('rename',item),blocked,item.name)}</span>
            <span data-action="archive">${this.button('archiveLocation',()=>this.begin('archive',item),blocked||item.archiveBlockedReason!==null,item.name)}</span>`}
      </div>${!item.archived && item.archiveBlockedReason!==null ? html`<p>${this.text(item.archiveBlockedReason)}</p>` : nothing}` : nothing}
    </li>`;
  }
  private review(blocked: boolean) {
    const editor=this.editor;if(editor===null)return nothing;
    const current=this.selected();
    const stale=editor.reviewRequired || (current!==undefined && editor.revision!==current.revision);
    const available=current!==undefined && this.allowed(editor.action,current);
    return html`<form class="location-review" aria-labelledby="location-review-title" novalidate @submit=${(event:SubmitEvent)=>this.change(event)}>
      <h4 id="location-review-title" tabindex="-1">${this.text(TITLE[editor.action])}</h4>
      <p>${current?.name ?? this.text('inventory_location_missing')}</p>
      ${editor.action==='rename' ? html`<vyp-ha-field .value=${this.renameDraft} ?disabled=${blocked}
        .state=${textFieldState({label:this.text('locationName'),required:true,
          description:this.text('locationNameHelp'),requiredMessage:this.text('invalid_inventory_location_name'),
          error:this.renameError===null?'':this.text(this.renameError)})}
        @ha-value-request=${(event:FieldValueEvent)=>{if(!this.blocked()){this.renameDraft=event.detail.value;this.renameError=null;}}}></vyp-ha-field>`
        : html`<p>${this.text(editor.action==='archive'?'locationArchiveHelp':'locationRestoreHelp')}</p>`}
      ${current && !available ? html`<p>${this.text('inventory_location_state_conflict')}</p>` : nothing}
      ${stale ? html`<p>${this.text('locationChangedReview')}</p>
        ${this.button('reviewCurrentLocation',()=>this.reviewCurrent(),blocked||!available)}` : nothing}
      ${editor.action==='archive' && current?.archiveBlockedReason ? html`<p>${this.text(current.archiveBlockedReason)}</p>` : nothing}
      <div class="actions">${this.submit(editor.action==='rename'?'saveLocationName':editor.action==='archive'?'confirmArchiveLocation':'confirmRestoreLocation',
        blocked||!available||stale||(editor.action==='rename'&&this.renameDraft.trim()===current?.name)
          ||(editor.action==='archive'&&current?.archiveBlockedReason!==null))}
        ${this.button('cancel',()=>this.cancel(),blocked)}</div>
    </form>`;
  }
  protected render() {
    const view=this.view;if(view?.report==null)return nothing;
    const locations=view.report.locations, manage=this.mayManage(),blocked=this.blocked();
    const active=locations.filter(item=>!item.archived), archived=locations.filter(item=>item.archived);
    return html`<vyp-ha-card .state=${cardState({title:this.text('locations'),headingLevel:3})}>
      <div class="location-content">
        <ul aria-label=${this.text('activeLocations')}><li>${this.text('pantry')}</li>${active.map(item=>this.row(item,manage,blocked))}</ul>
        ${archived.length===0 ? nothing : html`<details .open=${this.archivedOpen}
          @toggle=${(event:Event)=>{this.archivedOpen=(event.currentTarget as HTMLDetailsElement).open;}}>
          <summary>${this.text('archivedLocations')}</summary><ul>${archived.map(item=>this.row(item,manage,blocked))}</ul>
        </details>`}
        ${manage ? html`${this.review(blocked)}<form class="location-add" novalidate @submit=${(event:SubmitEvent)=>this.add(event)}>
          <vyp-ha-field .value=${this.addDraft} ?disabled=${blocked}
            .state=${textFieldState({label:this.text('locationName'),required:true,description:this.text('locationNameHelp'),
              requiredMessage:this.text('invalid_inventory_location_name'),error:this.addError===null?'':this.text(this.addError)})}
            @ha-value-request=${(event:FieldValueEvent)=>{if(!this.blocked()){this.addDraft=event.detail.value;this.addError=null;}}}></vyp-ha-field>
          ${this.submit('addLocation',blocked)}</form>` : html`<p>${this.text(view.scope.readOnly?'locationsReadOnly':'locationManagerRequired')}</p>`}
      </div></vyp-ha-card>`;
  }
}

registerButton();registerCard();registerField();
customElements.define('domus-storage-locations',DomusStorageLocations);
declare global {interface HTMLElementTagNameMap {'domus-storage-locations':DomusStorageLocations;}}
