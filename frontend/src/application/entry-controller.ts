import {entryDecision, setupPayload} from '../domain/entry';
import type {Authorization, Deployment, EntryDecision, SetupField} from '../domain/entry';
import type {Journal, JournalCommand, JournalContext, JournalRecord} from '../domain/journal';
import {EntryReadError} from './ports';
import type {CommandJournal, CommandResult, EntryClock, EntryEntropy, EntryRead, EntryServer,
  HouseholdFacts, VerifiedEntrySession} from './ports';

export type EntryNotice = 'journal_unavailable' | 'context_changed' | 'action_not_allowed'
  | 'previous_request_unresolved' | 'request_unavailable' | 'request_changed' | 'invalid_response'
  | 'authentication_required' | 'forbidden' | 'unavailable' | 'check_unconfirmed'
  | 'home_assistant_sign_out' | 'signed_out' | 'logout_unconfirmed';
type State = Readonly<{
  phase: 'idle' | 'loading' | 'ready' | 'sending' | 'closed';
  session: VerifiedEntrySession | null;
  authorization: Authorization | null;
  decision: EntryDecision | null;
  household: HouseholdFacts | null;
  journal: Journal | null;
  outcome: CommandResult | null;
  notice: EntryNotice | null;
  fields: readonly SetupField[];
  cleanup: 'confirmed' | 'unconfirmed' | null;
}>;
export type EntryView = State & Readonly<{busy: boolean}>;
type Intent = Readonly<{kind: 'new'; command: JournalCommand}>
  | Readonly<{kind: 'recover' | 'dismiss'; key: string}>;
type RetainedResult = Readonly<{context: JournalContext; expiresAt: number;
  outcome: CommandResult; notice: EntryNotice | null}>;
const retired = Symbol('retired entry read');
function sameContext(a: JournalContext, b: JournalContext): boolean {
  return a.installationId === b.installationId && a.channel === b.channel && a.subject === b.subject;
}
function sameOriginal(a: JournalRecord, b: JournalRecord): boolean {
  return a.key === b.key && a.action === b.action && a.createdAt === b.createdAt
    && a.expiresAt === b.expiresAt && a.operationId === b.operationId
    && JSON.stringify(a.payload) === JSON.stringify(b.payload);
}
function recoverable(request: JournalRecord, authorization: Authorization): boolean {
  if (request.action === 'setup') return authorization.state === 'unconfigured'
    ? authorization.setupAllowed
    : authorization.state === 'active' && authorization.permissions.includes('household.manage');
  return ['not_enrolled', 'pending', 'active'].includes(authorization.state);
}
function blank(phase: State['phase']): State {
  return Object.freeze({phase, session: null, authorization: null, decision: null, household: null,
    journal: null, outcome: null, notice: null, fields: Object.freeze([]), cleanup: null});
}

/** Semantic orchestration only. Neither a presentation decision nor a journal grants authority. */
export class EntryController {
  private state = blank('idle');
  private generation = 0;
  private running = false;
  private readonly reads = new Set<EntryRead<unknown>>();
  private retained: RetainedResult | null = null;
  constructor(private readonly deployment: Deployment, private readonly server: EntryServer,
    private readonly journal: CommandJournal, private readonly clock: EntryClock,
    private readonly entropy: EntryEntropy) {}

  get view(): EntryView {return Object.freeze({...this.state, busy: this.running});}
  private update(patch: Partial<State>): void {this.state = Object.freeze({...this.state, ...patch});}
  private invalidate(): number {
    this.generation++;
    const owned = [...this.reads]; this.reads.clear();
    for (const read of owned) {
      try {read.cancel();} catch {/* Cancellation failure cannot restore a retired generation. */}
    }
    this.journal.detach();
    return this.generation;
  }
  private begin(): number {const generation = this.invalidate(); this.state = blank('loading'); return generation;}
  private async read<T>(operation: EntryRead<T>, generation: number): Promise<T> {
    this.reads.add(operation);
    try {
      const value = await operation.result;
      if (generation !== this.generation) throw retired;
      return value;
    } finally {this.reads.delete(operation);}
  }
  private authenticationRequired(): void {
    this.state = Object.freeze({...blank('ready'),
      decision: entryDecision(this.deployment, null, null, 0), notice: 'authentication_required'});
  }
  private async load(generation: number): Promise<boolean> {
    try {
      const source = await this.read(this.server.session(), generation);
      if (source === null) {this.authenticationRequired(); return true;}
      if (source.deployment !== this.deployment) throw new EntryReadError('invalid_response');
      const session = Object.freeze({...source, context: Object.freeze({...source.context})});
      this.clock.anchor(session.serverTime);
      let decision = entryDecision(this.deployment, session, null, this.clock.now());
      if (decision.state === 'authentication_required') {this.authenticationRequired(); return true;}
      let authorization: Authorization | null = null, household: HouseholdFacts | null = null;
      if (session.householdApiAvailable) {
        const access = await this.read(this.server.authorization(session.context), generation);
        authorization = Object.freeze({...access, permissions: Object.freeze([...access.permissions])});
        decision = entryDecision(this.deployment, session, authorization, this.clock.now());
        if (decision.householdReadable)
          household = Object.freeze({...await this.read(this.server.household(session.context), generation)});
      }
      decision = entryDecision(this.deployment, session, authorization, this.clock.now());
      if (decision.state === 'authentication_required') {this.authenticationRequired(); return true;}
      if (this.retained !== null && (!sameContext(this.retained.context, session.context)
          || this.clock.now() >= this.retained.expiresAt)) this.retained = null;
      const permitted = authorization !== null && !['suspended', 'archived'].includes(authorization.state);
      let journal: Journal | null = null, notice: EntryNotice | null = null;
      if (permitted && !decision.readOnly) {
        try {journal = this.journal.open(session.context, this.clock.now());}
        catch {notice = 'journal_unavailable';}
      }
      const retained = permitted && !decision.readOnly ? this.retained : null;
      this.update({phase: 'ready', session, authorization, decision, household, journal,
        outcome: retained === null ? null : retained.outcome,
        notice: notice ?? (retained === null ? null : retained.notice)});
      return true;
    } catch (error) {
      if (generation !== this.generation) return false;
      this.journal.detach();
      const notice = error instanceof EntryReadError ? error.code : 'unavailable';
      if (notice === 'authentication_required') this.authenticationRequired();
      else this.state = Object.freeze({...blank('ready'), notice,
        decision: Object.freeze({state: 'unavailable', action: 'refresh', readOnly: false, householdReadable: false})});
      return false;
    }
  }
  async refresh(): Promise<void> {
    if (this.state.phase === 'closed') return;
    await this.load(this.begin());
  }
  /** Composition schedules this with its monotonic clock; no tick renews the session. */
  tick(): void {
    if (this.state.session === null) return;
    let decision: EntryDecision;
    let now: number;
    try {now = this.clock.now(); decision = entryDecision(this.deployment, this.state.session, this.state.authorization, now);}
    catch {this.invalidate(); this.authenticationRequired(); return;}
    if (decision.state === 'authentication_required') {this.invalidate(); this.authenticationRequired();}
    else {
      if (this.retained !== null && now >= this.retained.expiresAt) {this.retained = null; this.update({outcome: null});}
      const journal = this.state.journal;
      this.update({decision, journal: journal === null ? null
        : Object.freeze({...journal, records: Object.freeze(journal.records.filter(item => now < item.expiresAt))})});
    }
  }
  private currentContext(): JournalContext | null {
    this.tick();
    if (this.running || this.state.phase !== 'ready' || this.state.session === null
        || this.state.session.access !== 'full' || this.state.authorization === null || this.state.journal === null)
      return null;
    return this.state.session.context;
  }
  async submitSetup(name: unknown, timeZone: unknown): Promise<void> {
    if (this.running || this.state.phase === 'closed') return;
    const validation = setupPayload(name, timeZone);
    if (!validation.ok) {this.update({fields: validation.fields}); return;}
    await this.run({kind: 'new', command: {action: 'setup', payload: validation.payload}});
  }
  async requestMembership(): Promise<void> {
    await this.run({kind: 'new', command: {action: 'enroll', payload: {expected_revision: 0}}});
  }
  async recover(key: string): Promise<void> {await this.run({kind: 'recover', key});}
  async dismiss(key: string): Promise<void> {await this.run({kind: 'dismiss', key});}
  private async run(intent: Intent): Promise<void> {
    const context = this.currentContext();
    if (context === null) return;
    const original = intent.kind === 'new' ? null : this.state.journal!.records.find(item => item.key === intent.key);
    if (original === undefined) {this.update({notice: 'request_unavailable'}); return;}
    this.running = true;
    const generation = this.begin();
    try {
      if (!await this.load(generation) || generation !== this.generation) return;
      if (this.state.session === null) return;
      if (!sameContext(context, this.state.session.context)) {this.update({notice: 'context_changed'}); return;}
      if (this.state.session.access !== 'full' || this.state.authorization === null || this.state.journal === null) return;
      let request: JournalRecord;
      if (intent.kind === 'new') {
        const action = intent.command.action === 'setup' ? 'create_household' : 'request_membership';
        if (this.state.decision!.action !== action) {this.update({notice: 'action_not_allowed'}); return;}
        if (this.state.journal.records.some(item => item.stage === 'prepared' || item.stage === 'uncertain')) {
          this.update({notice: 'previous_request_unresolved'}); return;
        }
        const journal = this.journal.prepare(this.entropy.requestKey(), intent.command, this.clock.now());
        this.update({journal}); request = journal.records[journal.records.length - 1];
      } else {
        const found = this.state.journal.records.find(item => item.key === intent.key);
        if (found === undefined) {this.update({notice: 'request_unavailable'}); return;}
        if (!sameOriginal(original!, found)) {this.update({notice: 'request_changed'}); return;}
        request = found;
        if (intent.kind === 'dismiss') {
          this.update({journal: this.journal.forget(request.key, this.clock.now()), notice: null}); return;
        }
        if (request.stage === 'rejected' || !recoverable(request, this.state.authorization)) {
          this.update({notice: 'action_not_allowed'}); return;
        }
      }
      this.tick();
      if (generation !== this.generation) return;
      this.update({phase: 'sending', fields: Object.freeze([]), notice: null});
      let outcome: CommandResult;
      try {outcome = await this.server.send(Object.freeze({action: request.action, payload: request.payload,
        key: request.key}) as JournalCommand & Readonly<{key: string}>, context);}
      catch {outcome = Object.freeze({kind: 'uncertain'});}
      if (generation !== this.generation) return;
      let notice: EntryNotice | null = null;
      if (outcome.kind === 'receipt' && request.operationId !== null && request.operationId !== outcome.operationId) {
        this.update({phase: 'ready', notice: 'invalid_response'}); return;
      }
      try {
        if (outcome.kind === 'receipt') this.update({journal: this.journal.record(request.key,
          {stage: outcome.stage, operationId: outcome.operationId}, this.clock.now())});
        else if (request.operationId === null) this.update({journal: this.journal.record(request.key,
          {stage: outcome.kind === 'rejected' ? 'rejected' : 'uncertain', operationId: null}, this.clock.now())});
        else notice = 'check_unconfirmed';
      } catch {this.journal.detach(); this.update({journal: null}); notice = 'journal_unavailable';}
      this.retained = Object.freeze({context, expiresAt: request.expiresAt, outcome, notice});
      // A receipt is evidence of an earlier effect, never a renewal of the current session.
      this.tick();
      if (generation !== this.generation) return;
      this.update({outcome, notice});
      if (outcome.kind === 'rejected' && ['authentication_required', 'forbidden'].includes(outcome.reason)) {
        this.invalidate(); this.state = Object.freeze({...blank('ready'), outcome, notice: outcome.reason as EntryNotice,
          decision: outcome.reason === 'authentication_required' ? entryDecision(this.deployment, null, null, 0)
            : Object.freeze({state: 'unavailable', action: 'refresh', readOnly: false, householdReadable: false})});
        return;
      }
      this.update({phase: 'loading'});
      await this.load(generation);
    } catch {
      if (generation === this.generation) {
        this.journal.detach(); this.update({phase: 'ready', journal: null, notice: 'journal_unavailable'});
      }
    } finally {this.running = false;}
  }
  close(): void {this.invalidate(); this.retained = null; this.state = blank('closed');}
  async logout(): Promise<void> {
    if (this.state.phase === 'closed') return;
    this.close();
    const generation = this.generation;
    let cleanup: 'confirmed' | 'unconfirmed' = 'confirmed';
    try {this.journal.clear();} catch {cleanup = 'unconfirmed';}
    let notice: EntryNotice = 'home_assistant_sign_out';
    if (this.deployment === 'standalone') {
      try {notice = (await this.server.logout()).upstreamRevoked === true ? 'signed_out' : 'logout_unconfirmed';}
      catch {notice = 'logout_unconfirmed';}
    }
    if (generation === this.generation) this.update({cleanup, notice});
  }
}
