import type {Revision} from '../domain/administration';
import type {DraftScope} from './automation-drafts';
import {EntryReadError} from './ports';
import type {EntryEntropy, EntryRead} from './ports';

export interface ConfiguredAutomation {
  readonly ruleRevision: Revision;
  readonly controlRevision: Revision;
  readonly enabled: boolean;
  readonly title: string;
}

export interface AutomationConfiguration {
  readonly id: string;
  readonly latestRevision: Revision;
  readonly latestTitle: string;
  readonly control: ConfiguredAutomation | null;
}

export type AutomationCommand = Readonly<{kind: 'configure'; ruleId: string; ruleRevision: Revision;
  controlRevision: Revision | '0'; enabled: boolean}>
  | Readonly<{kind: 'run'; ruleId: string; ruleRevision: Revision; controlRevision: Revision}>;

export type AutomationExecutionRequest = AutomationCommand & Readonly<{key: string; scope: string}>;

export type AutomationExecutionResult = Readonly<{kind: 'committed' | 'historical';
  operationId: string; ruleRevision: Revision}> & (
  Readonly<{action: 'configure'; enabled: boolean}>
  | Readonly<{action: 'run'; taskOccurrenceId: string | null}>);

export type AutomationExecutionOutcome = AutomationExecutionResult
  | Readonly<{kind: 'stale' | 'disabled' | 'rejected' | 'missing'}>;

export interface AutomationExecutionServer {
  state(scope: DraftScope, id: string): EntryRead<AutomationConfiguration>;
  send(scope: DraftScope, request: AutomationExecutionRequest): EntryRead<AutomationExecutionOutcome>;
  original(scope: DraftScope, request: AutomationExecutionRequest): EntryRead<AutomationExecutionOutcome>;
}

export interface AutomationExecutionJournal {
  open(scope: string): AutomationExecutionRequest | null;
  save(request: AutomationExecutionRequest): void;
  clear(request: AutomationExecutionRequest): void;
}

export type AutomationExecutionIntent = 'enable' | 'disable' | 'run' | 'confirm' | 'cancel' | 'recover' | 'reload';
type Notice = 'denied' | 'unavailable' | 'uncertain' | 'stale' | 'disabled' | 'rejected';
interface Confirmation {readonly title: string; readonly command: AutomationCommand;}
interface DraftSelection {readonly id: string; readonly revision: Revision;}

export interface AutomationExecutionView {
  readonly configuration: AutomationConfiguration | null;
  readonly confirmation: Confirmation | null;
  readonly result: AutomationExecutionResult | null;
  readonly notice: Notice | null;
  readonly busy: boolean;
  readonly pending: boolean;
  readonly readOnly: boolean;
}

export class AutomationExecutionController {
  private scope: DraftScope | null = null;
  private selection: DraftSelection | null = null;
  private configuration: AutomationConfiguration | null = null;
  private confirmation: Confirmation | null = null;
  private result: AutomationExecutionResult | null = null;
  private notice: Notice | null = null;
  private pending: AutomationExecutionRequest | null = null;
  private owned: EntryRead<unknown> | null = null;

  constructor(private readonly server: AutomationExecutionServer, private readonly journal: AutomationExecutionJournal,
    private readonly entropy: EntryEntropy, private readonly publish: (view: AutomationExecutionView | null) => void) {}

  bind(scope: DraftScope | null, selection: DraftSelection | null): void {
    const sameScope = this.scope?.key === scope?.key;
    const sameSelection = this.selection?.id === selection?.id && this.selection?.revision === selection?.revision;
    const priorReadOnly = this.scope?.readOnly;
    this.scope = scope;
    this.selection = selection;
    if (sameScope && sameSelection) {
      if (priorReadOnly !== scope?.readOnly) this.emit();
      return;
    }
    if (!sameScope || this.pending === null) {
      this.owned?.cancel();
      this.owned = null;
      this.configuration = null;
      this.confirmation = null;
      this.result = null;
      this.notice = null;
    }
    if (!sameScope) {
      this.pending = null;
      if (scope !== null) {
        try {this.pending = this.journal.open(scope.key);}
        catch {this.notice = 'unavailable';}
        if (this.pending !== null) this.notice = 'uncertain';
      }
    }
    if (scope !== null && this.owned === null) void this.load(scope);
    else this.emit();
  }

  private target(): string | null {
    return this.pending?.ruleId ?? this.selection?.id ?? null;
  }

  private emit(): void {
    this.publish(this.scope === null || this.target() === null && this.result === null ? null : {
      configuration: this.configuration, confirmation: this.confirmation, result: this.result,
      notice: this.notice, busy: this.owned !== null, pending: this.pending !== null,
      readOnly: this.scope.readOnly,
    });
  }

  private retire(): void {
    this.configuration = null;
    this.confirmation = null;
    this.result = null;
    if (this.pending !== null) {
      try {this.journal.clear(this.pending);} catch {/* A read denial cannot grant access to journal data. */}
    }
    this.pending = null;
    this.notice = 'denied';
  }

  private async own<T>(request: EntryRead<T>, accept: (value: T) => void, onFailure: () => void): Promise<void> {
    this.owned = request;
    this.emit();
    try {
      const value = await request.result;
      if (this.owned === request) accept(value);
    } catch (error) {
      if (this.owned !== request) return;
      if (error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required'))
        this.retire();
      else onFailure();
    } finally {
      if (this.owned === request) {this.owned = null; this.emit();}
    }
  }

  private async load(scope: DraftScope): Promise<void> {
    const id = this.target();
    if (id === null) {this.configuration = null; this.emit(); return;}
    await this.own(this.server.state(scope, id), value => {this.configuration = value;}, () => {
      this.configuration = null;
      if (this.pending === null) this.notice = 'unavailable';
    });
  }

  private prepare(intent: 'enable' | 'disable' | 'run', configuration: AutomationConfiguration): void {
    const {id: ruleId, latestRevision, latestTitle, control} = configuration;
    if (intent === 'enable') {
      this.confirmation = {title: latestTitle, command: {kind: 'configure', ruleId, ruleRevision: latestRevision,
        controlRevision: control?.controlRevision ?? '0', enabled: true}};
    } else if (control?.enabled) {
      const {ruleRevision, controlRevision, title} = control;
      this.confirmation = {title, command: intent === 'run'
        ? {kind: 'run', ruleId, ruleRevision, controlRevision}
        : {kind: 'configure', ruleId, ruleRevision, controlRevision, enabled: false}};
    }
    this.emit();
  }

  async handle(intent: AutomationExecutionIntent): Promise<void> {
    const scope = this.scope;
    if (scope === null || this.owned !== null) return;
    if (intent === 'reload') {this.notice = null; await this.load(scope); return;}
    if (intent === 'recover') {await this.recover(scope); return;}
    if (intent === 'cancel') {this.confirmation = null; this.emit(); return;}
    if (scope.readOnly || this.pending !== null) return;
    if (intent === 'confirm') {
      const confirmation = this.confirmation;
      if (confirmation === null) return;
      let request: AutomationExecutionRequest;
      try {
        request = {...confirmation.command, key: this.entropy.requestKey(), scope: scope.key};
        this.journal.save(request);
      } catch {this.notice = 'unavailable'; this.emit(); return;}
      this.pending = request;
      this.confirmation = null;
      this.result = null;
      this.notice = null;
      await this.complete(scope, request, this.server.send(scope, request));
    } else if (this.configuration !== null) this.prepare(intent, this.configuration);
  }

  private async recover(scope: DraftScope): Promise<void> {
    const request = this.pending;
    if (request === null) return;
    const missing = await this.complete(scope, request, this.server.original(scope, request));
    if (missing && this.pending === request && this.scope?.key === scope.key && !this.scope.readOnly)
      await this.complete(scope, request, this.server.send(scope, request));
  }

  private async complete(scope: DraftScope, request: AutomationExecutionRequest,
    transport: EntryRead<AutomationExecutionOutcome>): Promise<boolean> {
    let missing = false, refresh = false;
    await this.own(transport, value => {
      if (value.kind === 'missing') {missing = true; this.notice = 'uncertain'; return;}
      this.journal.clear(request);
      this.pending = null;
      if ('action' in value) {this.result = value; this.notice = null;}
      else this.notice = value.kind;
      refresh = true;
    }, () => {this.notice = 'uncertain';});
    if (refresh && this.scope?.key === scope.key) await this.load(scope);
    return missing;
  }
}
