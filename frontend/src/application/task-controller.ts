/** Task workflows coordinate current identity, durable original intents and server-owned actions. */
import {JournalError} from '../domain/journal';
import {isCategoryCommand, taskCommand, taskIdentifier} from '../domain/tasks';
import type {TaskAccess, TaskCommand, TaskDetail, TaskMaterialUsage, TaskPage, TaskPriority, TaskScheduleDraft} from '../domain/tasks';
import {EntryReadError} from './ports';
import type {Revision} from '../domain/administration';
import type {ReviewedAllocation} from '../domain/point-allocation';
import type {Deployment} from '../domain/entry';
import type {EntryClock, EntryEntropy, EntryRead, EntryServer, VerifiedEntrySession} from './ports';
import type {TaskCommandResult, TaskJournalPort, TaskJournalScope, TaskRecord, TaskServer} from './task-ports';

export type TaskNotice = 'authentication_required' | 'forbidden' | 'unavailable' | 'invalid_response'
  | 'invalid_input' | 'conflict' | 'read_only' | 'journal_unavailable' | 'context_changed'
  | 'category_unavailable' | 'journal_capacity' | 'previous_request_unresolved' | 'action_not_allowed' | 'request_changed' | 'request_unavailable';
interface State {
  readonly phase: 'idle' | 'loading' | 'ready' | 'closed';
  readonly session: VerifiedEntrySession | null; readonly access: TaskAccess | null;
  readonly scopeKey: string | null; readonly readOnly: boolean;
  readonly page: TaskPage | null; readonly detail: TaskDetail | null;
  readonly records: readonly TaskRecord[] | null; readonly outcome: TaskCommandResult | null; readonly notice: TaskNotice | null;
}
export type TaskView = Readonly<State & {busy: boolean}>;
function blank(phase: State['phase']): State {
  return Object.freeze({phase, session: null, access: null, scopeKey: null, readOnly: true,
    page: null, detail: null, records: null, outcome: null, notice: null});
}
function scope(session: VerifiedEntrySession, access: TaskAccess): TaskJournalScope {
  return Object.freeze({context: session.context, householdId: access.householdId, memberId: access.memberId});
}
function scopeKey(selected: TaskJournalScope): string {
  const {context} = selected;
  return JSON.stringify([context.installationId, context.channel, context.subject, selected.householdId, selected.memberId]);
}
const retired = Symbol('retired task request');
export class TaskController {
  private state: State = blank('idle');
  private generation = 0;
  private running = false;
  private closed = false;
  private readonly reads = new Set<EntryRead<unknown>>();
  constructor(private readonly deployment: Deployment, private readonly identity: Pick<EntryServer, 'session'>,
    private readonly server: TaskServer, private readonly journal: TaskJournalPort,
    private readonly clock: EntryClock, private readonly entropy: EntryEntropy) {}
  get view(): TaskView {return Object.freeze({...this.state, busy: this.running});}
  private update(patch: Partial<State>): void {this.state = Object.freeze({...this.state, ...patch});}
  private invalidate(): number {
    this.generation++; const owned = [...this.reads]; this.reads.clear();
    for (const read of owned) {try {read.cancel();} catch {/* Retired callbacks remain fenced. */}}
    this.journal.detach(); return this.generation;
  }
  private async read<T>(operation: EntryRead<T>, generation: number): Promise<T> {
    this.reads.add(operation);
    try {
      const value = await operation.result;
      if (this.closed || generation !== this.generation) throw retired;
      if (this.state.session !== null && this.clock.now() >= this.state.session.expiresAt)
        throw new EntryReadError('authentication_required');
      return value;
    } finally {this.reads.delete(operation);}
  }
  private async fresh(generation: number): Promise<void> {
    const source = await this.read(this.identity.session(), generation);
    if (source === null) throw new EntryReadError('authentication_required');
    if (source.deployment !== this.deployment) throw new EntryReadError('invalid_response');
    this.clock.anchor(source.serverTime);
    if (this.clock.now() >= source.expiresAt) throw new EntryReadError('authentication_required');
    if (!source.householdApiAvailable) throw new EntryReadError('unavailable');
    const session = Object.freeze({...source, context: Object.freeze({...source.context})});
    this.update({session, readOnly: source.access !== 'full'});
    const current = await this.read(this.server.access(session.context), generation);
    const access = Object.freeze({...current}), selected = scope(session, access);
    let records: readonly TaskRecord[] | null = null;
    try {records = this.journal.open(selected, this.clock.now());} catch {/* Reads remain available; writes require confirmed storage. */}
    this.update({access, scopeKey: scopeKey(selected), records, notice: records === null ? 'journal_unavailable' : null});
  }
  private async run(work: (prior: State, generation: number) => Promise<void>): Promise<void> {
    if (this.closed || this.running) return;
    const prior = this.state, generation = this.invalidate(); this.running = true; this.state = blank('loading');
    try {await this.fresh(generation); await work(prior, generation);}
    catch (error) {
      if (generation !== this.generation || this.closed || error === retired) return;
      const notice = error instanceof EntryReadError ? error.code : 'unavailable';
      if (notice === 'authentication_required' || notice === 'forbidden') this.state = Object.freeze({...blank('ready'), notice});
      else this.update({notice});
    } finally {
      if (generation === this.generation && !this.closed) {this.running = false; this.update({phase: 'ready'});}
    }
  }
  private async facts(generation: number, selected: string | null, cursor: string | null = null): Promise<void> {
    const session = this.state.session!, access = this.state.access!;
    const page = await this.read(this.server.list(session.context, cursor), generation); this.update({page});
    if (selected !== null) this.update({detail: await this.read(this.server.detail(selected, access.householdId, session.context), generation)});
  }
  refresh(): Promise<void> {
    return this.run(async (prior, generation) => {
      const same = this.state.scopeKey === prior.scopeKey;
      if (same) this.update({outcome: prior.outcome});
      await this.facts(generation, same ? prior.detail?.occurrenceId ?? null : null);
    });
  }
  more(): Promise<void> {
    const cursor = this.state.page?.nextCursor;
    if (!cursor) return Promise.resolve();
    return this.run(async (prior, generation) => {
      if (this.state.scopeKey !== prior.scopeKey) {this.update({notice: 'context_changed'}); return;}
      await this.facts(generation, null, cursor);
    });
  }
  select(value: unknown): Promise<void> {
    let id: string; try {id = taskIdentifier(value);} catch {this.update({notice: 'invalid_input'}); return Promise.resolve();}
    return this.run(async (prior, generation) => {
      if (this.state.scopeKey !== prior.scopeKey) {this.update({notice: 'context_changed'}); return;}
      const detail = await this.read(this.server.detail(id, this.state.access!.householdId, this.state.session!.context), generation);
      this.update({page: prior.page, detail, outcome: prior.outcome});
    });
  }
  private accepted(command: TaskCommand): boolean {
    const access = this.state.access!;
    if (command.action === 'task.create') {
      if (command.payload.category_id !== undefined && !access.categoryCatalog?.categories.some(item => item.id === command.payload.category_id))
        {this.update({notice: 'category_unavailable'}); return false;}
      return access.canCreate && (command.payload.overrides === undefined || access.canConfigure === true);
    }
    if (isCategoryCommand(command)) {
      if (!access.categoryCatalog?.canManage) return false;
      if (command.action === 'task.category.create') return true;
      const current = access.categoryCatalog.categories.find(item => item.id === command.categoryId);
      if (current?.revision !== command.payload.expected_revision) {this.update({notice: 'conflict'}); return false;}
      return true;
    }
    const detail = this.state.detail!;
    if (detail.occurrenceId !== command.occurrenceId) return false;
    if (detail.revision !== command.payload.expected_revision) {this.update({notice: 'conflict'}); return false;}
    const action = command.action === 'task.verify' ? command.payload.decision === 'approved' ? 'approve' : 'reject' : command.action.slice(5);
    return detail.allowedActions.includes(action);
  }
  private save(key: string, outcome: TaskCommandResult): void {
    const stage = outcome.kind === 'receipt' ? outcome.stage : outcome.kind;
    try {this.update({records: this.journal.record(key, stage, outcome.kind === 'receipt' ? outcome.operationId : null, this.clock.now())});}
    catch {this.update({notice: 'journal_unavailable'});}
    this.update({outcome});
  }
  private execute(value: unknown): Promise<void> {
    if (this.closed || this.running || this.state.access === null) return Promise.resolve();
    const command = taskCommand(value);
    if (command === undefined) {this.update({notice: 'invalid_input'}); return Promise.resolve();}
    return this.run(async (prior, generation) => {
      if (this.state.scopeKey !== prior.scopeKey) {this.update({notice: 'context_changed'}); return;}
      this.update({page: prior.page});
      if (this.state.readOnly) {this.update({notice: 'read_only'}); return;}
      if ('occurrenceId' in command) this.update({detail: await this.read(this.server.detail(command.occurrenceId, this.state.access!.householdId, this.state.session!.context), generation)});
      if (!this.accepted(command)) {if (this.state.notice !== 'conflict' && this.state.notice !== 'category_unavailable') this.update({notice: 'action_not_allowed'}); return;}
      if (this.state.records === null) {this.update({notice: 'journal_unavailable'}); return;}
      if (this.state.records.some(item => item.stage === 'prepared' || item.stage === 'uncertain')) {this.update({notice: 'previous_request_unresolved'}); return;}
      let key: string;
      try {key = this.entropy.requestKey(); this.update({records: this.journal.prepare(key, command, this.clock.now())});}
      catch (error) {this.update({notice: error instanceof JournalError && (error.code === 'journal_capacity' || error.code === 'journal_too_large')
        ? 'journal_capacity' : 'journal_unavailable'}); return;}
      const outcome = await this.server.send({key, command}, this.state.session!.context);
      if (this.closed || generation !== this.generation) return;
      this.save(key, outcome);
      if (outcome.kind === 'rejected' && (outcome.reason === 'authentication_required' || outcome.reason === 'forbidden')) {
        this.state = Object.freeze({...blank('ready'), notice: outcome.reason}); return;
      }
      if (this.clock.now() >= this.state.session!.expiresAt) throw new EntryReadError('authentication_required');
      if (outcome.kind === 'receipt') await this.receiptFacts(command, outcome.occurrenceId, prior, generation);
    });
  }
  private async receiptFacts(command: TaskCommand, occurrence: string | null, prior: State, generation: number): Promise<void> {
    if (isCategoryCommand(command)) {
      const current = await this.read(this.server.access(this.state.session!.context), generation);
      if (scopeKey(scope(this.state.session!, current)) !== prior.scopeKey) {
        this.journal.detach(); this.state = Object.freeze({...blank('ready'), notice: 'context_changed'}); return;
      }
      this.update({access: Object.freeze({...current})});
      await this.facts(generation, prior.detail?.occurrenceId ?? null);
      return;
    }
    await this.facts(generation, occurrence);
  }
  create(title: unknown, description: unknown, priority: TaskPriority, draft?: TaskScheduleDraft, categoryId?: string, basePointsMinor?: number): Promise<void> {
    const schedule = draft === undefined ? {} : {schedule: {draft, policy: this.state.access?.schedulePolicy}};
    return this.execute({action: 'task.create', payload: {expected_revision: 0, title, description, priority, ...schedule,
      ...categoryId === undefined ? {} : {category_id: categoryId},
      ...basePointsMinor === undefined ? {} : {overrides: {point_value_minor: basePointsMinor}}}});
  }
  createCategory(label: string): Promise<void> {
    return this.execute({action: 'task.category.create', payload: {expected_revision: 0, label}});
  }
  renameCategory(categoryId: string, revision: Revision, label: string): Promise<void> {
    return this.execute({action: 'task.category.rename', categoryId, payload: {expected_revision: revision, label}});
  }
  archiveCategory(categoryId: string, revision: Revision): Promise<void> {
    return this.execute({action: 'task.category.archive', categoryId, payload: {expected_revision: revision}});
  }
  claim(): Promise<void> {
    const work = this.state.detail;
    return work === null ? Promise.resolve() : this.execute({action: 'task.claim', occurrenceId: work.occurrenceId, payload: {expected_revision: work.revision}});
  }
  complete(materialUsages: readonly TaskMaterialUsage[] | null, reviewed?: ReviewedAllocation): Promise<void> {
    const work = this.state.detail, member = this.state.access?.memberId;
    if (work === null || member === undefined) return Promise.resolve();
    if (reviewed !== undefined && (reviewed.occurrenceId !== work.occurrenceId || reviewed.revision !== work.revision)) {
      this.update({notice: 'conflict'}); return Promise.resolve();
    }
    let performedAt: string; try {performedAt = String(this.clock.now());} catch {this.update({notice: 'unavailable'}); return Promise.resolve();}
    return this.execute({action: 'task.complete', occurrenceId: work.occurrenceId, payload: {expected_revision: work.revision,
      performer_ids: reviewed?.performerIds ?? [member], performed_at: performedAt, material_usages: materialUsages,
      ...reviewed === undefined ? {} : {allocation_fingerprint: reviewed.fingerprint},
      ...reviewed?.manualShares === undefined ? {} : {manual_shares: reviewed.manualShares}}});
  }
  verify(decision: 'approved' | 'rejected', reason: unknown): Promise<void> {
    const work = this.state.detail;
    return work?.cycle == null ? Promise.resolve() : this.execute({action: 'task.verify', occurrenceId: work.occurrenceId,
      payload: {expected_revision: work.revision, cycle_id: work.cycle.cycleId, decision, reason}});
  }
  reopen(reason: unknown): Promise<void> {
    const work = this.state.detail;
    return work?.cycle == null ? Promise.resolve() : this.execute({action: 'task.reopen', occurrenceId: work.occurrenceId,
      payload: {expected_revision: work.revision, cycle_id: work.cycle.cycleId, reason}});
  }
  recover(key: string): Promise<void> {
    const original = this.state.records?.find(item => item.key === key);
    if (!original) return Promise.resolve();
    return this.run(async (prior, generation) => {
      if (this.state.scopeKey !== prior.scopeKey) {this.update({notice: 'context_changed'}); return;}
      const current = this.state.records?.find(item => item.key === key);
      if (current === undefined || JSON.stringify(current) !== JSON.stringify(original)) {this.update({notice: 'request_changed'}); return;}
      this.update({page: prior.page});
      const outcome = await this.read(this.server.original({key, command: current.command, operationId: current.operationId}, this.state.session!.context), generation);
      this.save(key, outcome); await this.receiptFacts(current.command, outcome.occurrenceId, prior, generation);
    });
  }
  dismiss(key: string): Promise<void> {
    return this.run(async prior => {
      if (this.state.scopeKey !== prior.scopeKey) {this.update({notice: 'context_changed'}); return;}
      try {this.update({records: this.journal.forget(key, this.clock.now()), page: prior.page, detail: prior.detail});}
      catch {this.update({notice: 'request_unavailable'});}
    });
  }
  tick(): void {
    if (this.closed || this.state.session === null) return;
    try {
      const now = this.clock.now();
      if (now < this.state.session.expiresAt) {
        if (this.state.records?.some(record => now >= record.expiresAt)) {
          try {this.update({records: this.journal.open(scope(this.state.session, this.state.access!), now)});}
          catch {this.journal.detach(); this.update({records: null, notice: 'journal_unavailable'});}
        }
        return;
      }
    } catch {/* Unknown time cannot extend the lease. */}
    this.invalidate(); this.running = false; this.state = Object.freeze({...blank('ready'), notice: 'authentication_required'});
  }
  close(): void {this.closed = true; this.invalidate(); this.running = false; this.state = blank('closed');}
}
