import type {Revision} from '../domain/administration';
import type {JournalContext} from '../domain/journal';
import {taskText} from '../domain/tasks';
import type {AutomationPreviewDraft} from './automation-preview';
import {isDailyTime} from './automation-schedule-preview';
import {EntryReadError} from './ports';
import type {EntryEntropy, EntryRead} from './ports';

export interface DraftScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly memberId: string;
  readonly readOnly: boolean;
}
export interface DraftSummary {
  readonly id: string;
  readonly revision: Revision;
  readonly title: string;
}
export type DraftCondition = Readonly<{kind: 'stock_below_minimum'; product_id: string}>
  | Readonly<{kind: 'not'; child: DraftCondition}>
  | Readonly<{kind: 'all' | 'any'; children: readonly DraftCondition[]}>;
export type DraftTrigger = 'manual' | 'daily';
export interface EditableAutomationRule extends AutomationPreviewDraft {
  readonly dailyTime?: string;
}
export interface SavedAutomationDraft extends DraftSummary {
  readonly dailyTime?: string;
  readonly condition: DraftCondition | null;
}
export interface DraftPage {
  readonly drafts: readonly DraftSummary[];
  readonly next: string | null;
}
export interface DraftRequest {
  readonly key: string;
  readonly scope: string;
  readonly ruleId: string | null;
  readonly revision: Revision | '0';
  readonly rule: EditableAutomationRule;
}
export type DraftOutcome = Readonly<{kind: 'committed' | 'historical'; id: string; revision: Revision; operationId: string}>
  | Readonly<{kind: 'conflict' | 'rejected' | 'missing'}>;
export interface AutomationDraftServer {
  list(scope: DraftScope, after: string | null): EntryRead<DraftPage>;
  reopen(scope: DraftScope, id: string): EntryRead<SavedAutomationDraft>;
  previewSaved(scope: DraftScope, draft: SavedAutomationDraft): EntryRead<boolean>;
  send(scope: DraftScope, request: DraftRequest): EntryRead<DraftOutcome>;
  original(scope: DraftScope, request: DraftRequest): EntryRead<DraftOutcome>;
}
export interface AutomationDraftJournal {
  open(scope: string): DraftRequest | null;
  save(request: DraftRequest): void;
  clear(request: DraftRequest): void;
}

type Notice = 'unavailable' | 'invalid_title' | 'invalid_daily_time' | 'uncertain' | 'rejected' | 'conflict' | 'saved' | 'historical';
interface ReadyDrafts {
  readonly state: 'ready';
  readonly trigger: DraftTrigger;
  readonly page: DraftPage;
  readonly after: string | null;
  readonly selected: Readonly<{id: string; revision: Revision}> | null;
  readonly locked: SavedAutomationDraft | null;
  readonly competing: SavedAutomationDraft | null;
  readonly conflict: boolean; // A read failure can replace the notice while saving stays blocked.
  readonly operationId: string | null;
  readonly preview: boolean | null;
  readonly busy: boolean;
  readonly pending: boolean;
  readonly readOnly: boolean;
  readonly notice: Notice | null;
}
export type AutomationDraftView = ReadyDrafts | Readonly<{state: 'loading' | 'denied' | 'unavailable'}>;
export type AutomationDraftIntent = Readonly<{type: 'open'; id: string}>
  | Readonly<{type: 'trigger'; trigger: DraftTrigger}>
  | Readonly<{type: 'retry' | 'next' | 'first' | 'new' | 'save' | 'recover' | 'review' | 'rebase' | 'preview_saved'}>;

function editable(draft: SavedAutomationDraft): EditableAutomationRule | null {
  const {title, condition, dailyTime} = draft;
  if (condition !== null && condition.kind !== 'stock_below_minimum') return null;
  return {title, productId: condition?.product_id ?? null, ...(dailyTime === undefined ? {} : {dailyTime})};
}

export class AutomationDraftController {
  private scope: DraftScope | null = null;
  private visible = false;
  private ready: ReadyDrafts | null = null;
  private owned: EntryRead<unknown> | null = null;
  private pending: DraftRequest | null = null;

  constructor(private readonly server: AutomationDraftServer, private readonly journal: AutomationDraftJournal,
    private readonly entropy: EntryEntropy, private readonly edit: (rule: EditableAutomationRule) => void,
    private readonly publish: (view: AutomationDraftView | null) => void) {}

  bind(scope: DraftScope | null, visible = false): void {
    const prior = this.scope;
    visible = scope !== null && visible;
    const same = prior?.key === scope?.key;
    this.scope = scope;
    if (same && this.visible === visible) {
      if (this.ready !== null && scope !== null && prior?.readOnly !== scope.readOnly) this.set({readOnly: scope.readOnly});
      return;
    }
    this.cancel();
    if (!same) {
      this.ready = null;
      this.pending = null;
    }
    this.visible = visible;
    if (visible && scope !== null) void this.list(scope, this.ready?.after ?? null);
    else this.publish(null);
  }

  private cancel(): void {
    this.owned?.cancel();
    this.owned = null;
  }

  private set(patch: Partial<ReadyDrafts>): void {
    if (this.ready === null) return;
    this.ready = {...this.ready, ...patch};
    this.publish(this.ready);
  }

  private retire(scope: DraftScope): void {
    this.ready = null;
    this.pending = null;
    try {
      const saved = this.journal.open(scope.key);
      if (saved !== null) this.journal.clear(saved);
    } catch {/* Failure to remove local bytes never grants access to them. */}
    this.edit({title: '', productId: null});
    this.publish({state: 'denied'});
  }

  private async run<T>(scope: DraftScope, request: EntryRead<T>, use: (value: T) => void, fail: () => void): Promise<void> {
    this.owned = request;
    this.set({busy: true});
    try {
      const value = await request.result;
      if (this.owned === request) use(value);
    } catch (error) {
      if (this.owned !== request) return;
      if (error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required')) {
        this.retire(scope);
      } else fail();
    } finally {
      if (this.owned === request) {this.owned = null; this.set({busy: false});}
    }
  }

  private async list(scope: DraftScope, after: string | null): Promise<void> {
    if (this.ready === null) this.publish({state: 'loading'});
    await this.run(scope, this.server.list(scope, after), page => {
      if (this.ready === null) {
        this.pending = this.journal.open(scope.key);
        const recover = this.pending;
        this.ready = {state: 'ready', trigger: recover?.rule.dailyTime === undefined ? 'manual' : 'daily',
          page, after, selected: recover?.ruleId == null ? null
          : {id: recover.ruleId, revision: recover.revision as Revision}, locked: null,
          competing: null, conflict: false, operationId: null, preview: null, busy: true, pending: recover !== null,
          readOnly: this.scope!.readOnly, notice: recover === null ? null : 'uncertain'};
        if (recover !== null) this.edit(recover.rule);
      }
      this.set({page, after});
    }, () => {
      if (this.ready === null) this.publish({state: 'unavailable'});
      else this.set({notice: 'unavailable'});
    });
  }

  async handle(intent: AutomationDraftIntent | undefined, input: AutomationPreviewDraft | null,
    dailyTime = ''): Promise<void> {
    const scope = this.scope, ready = this.ready;
    if (intent === undefined || scope === null || !this.visible || this.owned !== null) return;
    if (intent.type === 'retry') {await this.list(scope, ready?.after ?? null); return;}
    if (ready === null) return;
    if (intent.type === 'recover') {await this.recover(scope); return;}
    if (intent.type === 'first' && ready.after !== null) {await this.list(scope, null); return;}
    if (intent.type === 'next' && ready.page.next !== null) {await this.list(scope, ready.page.next); return;}
    if (this.pending !== null) return;
    if (intent.type === 'new') {
      this.edit({title: '', productId: null});
      this.set({trigger: 'manual', selected: null, locked: null, competing: null, conflict: false,
        notice: null, preview: null, operationId: null});
    } else if (intent.type === 'trigger' && ready.locked === null && !scope.readOnly) {
      this.set({trigger: intent.trigger, notice: null});
    } else if (intent.type === 'open' && ready.page.drafts.some(draft => draft.id === intent.id)) {
      await this.open(scope, intent.id, false);
    } else if (intent.type === 'review' && ready.conflict && ready.selected !== null) {
      this.set({competing: null, notice: 'conflict'});
      await this.open(scope, ready.selected.id, true);
    } else if (intent.type === 'rebase' && ready.competing !== null && !scope.readOnly) {
      const competing = ready.competing;
      if (editable(competing) !== null) this.set({selected: competing, competing: null, conflict: false, notice: null});
    } else if (intent.type === 'preview_saved' && ready.locked !== null) {
      this.set({notice: null, preview: null});
      await this.run(scope, this.server.previewSaved(scope, ready.locked), preview => this.set({preview}),
        () => this.set({notice: 'unavailable'}));
    } else if (intent.type === 'save' && input !== null && !scope.readOnly
        && ready.locked === null && !ready.conflict) {
      await this.save(scope, ready, input, dailyTime);
    }
  }

  private async open(scope: DraftScope, id: string, review: boolean): Promise<void> {
    await this.run(scope, this.server.reopen(scope, id), draft => {
      if (review) {this.set({competing: draft}); return;}
      const rule = editable(draft);
      const {title, dailyTime} = draft;
      this.edit(rule ?? {title, productId: null, ...(dailyTime === undefined ? {} : {dailyTime})});
      this.set({trigger: dailyTime === undefined ? 'manual' : 'daily',
        selected: draft, locked: rule === null ? draft : null, competing: null, conflict: false,
        notice: null, preview: null, operationId: null});
    }, () => this.set({notice: 'unavailable'}));
  }

  private async save(scope: DraftScope, ready: ReadyDrafts, input: AutomationPreviewDraft, dailyTime: string): Promise<void> {
    let title: string;
    try {title = taskText(input.title, 160, true);}
    catch {this.set({notice: 'invalid_title'}); return;}
    const daily = ready.trigger === 'daily';
    if (daily && !isDailyTime(dailyTime)) {this.set({notice: 'invalid_daily_time'}); return;}
    let request: DraftRequest;
    try {
      request = {key: this.entropy.requestKey(), scope: scope.key, ruleId: ready.selected?.id ?? null,
        revision: ready.selected?.revision ?? '0',
        rule: {title, productId: input.productId, ...(daily ? {dailyTime} : {})}};
      this.journal.save(request);
    } catch {this.set({notice: 'unavailable'}); return;}
    this.pending = request;
    this.set({pending: true, notice: null, operationId: null});
    await this.send(scope, request, this.server.send(scope, request));
  }

  private async recover(scope: DraftScope): Promise<void> {
    const request = this.pending;
    if (request === null) return;
    const original = await this.send(scope, request, this.server.original(scope, request));
    if (original && this.pending === request && !this.scope?.readOnly) {
      await this.send(scope, request, this.server.send(scope, request));
    }
  }

  private async send(scope: DraftScope, request: DraftRequest, owned: EntryRead<DraftOutcome>): Promise<boolean> {
    let retry = false;
    let refresh = false;
    await this.run(scope, owned, outcome => {
      if (outcome.kind === 'missing') {retry = true; return;}
      this.journal.clear(request);
      this.pending = null;
      if (outcome.kind === 'committed') {
        this.set({pending: false, selected: {id: outcome.id, revision: outcome.revision}, notice: 'saved',
          operationId: outcome.operationId, competing: null});
        refresh = true;
      } else if (outcome.kind === 'historical') {
        this.set({pending: false, selected: null, notice: 'historical', operationId: outcome.operationId});
        refresh = true;
      } else this.set({pending: false, conflict: outcome.kind === 'conflict', notice: outcome.kind});
    }, () => this.set({notice: 'uncertain'}));
    if (refresh && this.visible && this.scope?.key === scope.key) await this.list(scope, null);
    return retry;
  }
}
