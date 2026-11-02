/** Current-fact orchestration; neither browser state nor a stored intent grants backend authority. */
import {administrationCommand} from '../domain/administration-commands';
import {administrationAllowed as allowed} from '../domain/administration-authorization';
import type {AdministrationCommand} from '../domain/administration-commands';
import {nextRevision} from '../domain/administration';
import type {Revision} from '../domain/administration';
import type {AdministrationJournalView, AdministrationRecord} from '../domain/administration-journal';
import type {AdministrationAccess, AdministrationCapabilities, AdministrationPolicy, AdministrationReceipt,
  Directory, OwnPreferences, Roster} from '../domain/administration-views';
import {entryDecision} from '../domain/entry';
import type {Deployment} from '../domain/entry';
import type {JournalContext} from '../domain/journal';
import {EntryReadError} from './ports';
import type {EntryClock, EntryEntropy, EntryRead, EntryServer, HouseholdFacts, ReadFault, VerifiedEntrySession} from './ports';
import type {AdministrationCommandResult, AdministrationJournalPort, AdministrationOriginal, AdministrationServer} from './administration-ports';

type Facts = {household: HouseholdFacts | null; roster: Roster | null; policy: AdministrationPolicy | null;
  directory: Directory | null; preferences: OwnPreferences | null};
export type AdministrationNotice = ReadFault | 'api_unavailable' | 'inactive' | 'read_only' | 'access_changed'
  | 'journal_unavailable' | 'invalid_input' | 'action_not_allowed' | 'request_unavailable' | 'request_changed'
  | 'context_changed' | 'conflict' | 'revision_exhausted' | 'previous_request_unresolved' | 'check_unconfirmed';
type State = Readonly<Facts & {phase: 'idle' | 'loading' | 'ready' | 'sending' | 'closed';
  session: VerifiedEntrySession | null; access: AdministrationAccess | null; capabilities: AdministrationCapabilities | null;
  journal: AdministrationJournalView | null; outcome: AdministrationCommandResult | null;
  errors: Readonly<Partial<Record<keyof Facts, ReadFault>>>; notice: AdministrationNotice | null}>;
export type AdministrationView = State & Readonly<{busy: boolean}>;
type Intent = Readonly<{kind: 'new'; command: AdministrationCommand}> | Readonly<{kind: 'recover' | 'dismiss'; key: string}>;
type Retained = Readonly<{context: JournalContext; request: AdministrationRecord;
  outcome: AdministrationCommandResult; notice: AdministrationNotice | null}>;
const retired = Symbol('retired administration read');
function blank(phase: State['phase']): State {
  return Object.freeze({phase, session: null, access: null, capabilities: null, journal: null, outcome: null,
    household: null, roster: null, policy: null, directory: null, preferences: null,
    errors: Object.freeze({}), notice: null});
}
function sameContext(a: JournalContext, b: JournalContext): boolean {
  return a.installationId === b.installationId && a.channel === b.channel && a.subject === b.subject;
}
function commandOf(record: AdministrationRecord): AdministrationCommand {
  const {action, payload} = record;
  return administrationCommand('memberId' in record ? {action, payload, memberId: record.memberId} : {action, payload});
}
function sameAggregate(a: AdministrationCommand, b: AdministrationCommand): boolean {
  return a.action === b.action && (!('memberId' in a) || ('memberId' in b && a.memberId === b.memberId));
}
function fault(error: unknown): ReadFault {return error instanceof EntryReadError ? error.code : 'unavailable';}

export class AdministrationController {
  private state = blank('idle');
  private generation = 0;
  private running = false;
  private opened: AdministrationJournalView | null = null;
  private retained: Retained | null = null;
  private readonly reads = new Set<EntryRead<unknown>>();
  constructor(private readonly deployment: Deployment, private readonly identity: Pick<EntryServer, 'session'>,
    private readonly server: AdministrationServer, private readonly journal: AdministrationJournalPort,
    private readonly clock: EntryClock, private readonly entropy: EntryEntropy) {}
  get view(): AdministrationView {return Object.freeze({...this.state, busy: this.running});}
  private update(patch: Partial<State>): void {this.state = Object.freeze({...this.state, ...patch});}
  private invalidate(): number {
    this.generation++;
    const reads = [...this.reads]; this.reads.clear();
    for (const read of reads) {try {read.cancel();} catch {/* The generation still retires the result. */}}
    this.journal.detach(); this.opened = null; return this.generation;
  }
  private begin(): number {const generation = this.invalidate(); this.state = blank('loading'); return generation;}
  private async read<T>(read: EntryRead<T>, generation: number): Promise<T> {
    this.reads.add(read);
    try {const value = await read.result; if (generation !== this.generation) throw retired; return value;}
    finally {this.reads.delete(read);}
  }
  private visible(journal: AdministrationJournalView, access: AdministrationAccess): AdministrationJournalView {
    return Object.freeze({...journal, records: Object.freeze(journal.records.filter(record => allowed(access, record)))});
  }
  private showJournal(journal: AdministrationJournalView): void {
    this.opened = journal; this.update({journal: this.visible(journal, this.state.access!)});
  }
  private block(notice: AdministrationNotice): void {
    this.invalidate(); this.retained = null; this.state = Object.freeze({...blank('ready'), notice});
  }
  private ensureTime(session: VerifiedEntrySession): number {
    const now = this.clock.now();
    if (entryDecision(this.deployment, session, null, now).state === 'authentication_required')
      throw new EntryReadError('authentication_required');
    return now;
  }
  private async load(generation: number): Promise<boolean> {
    try {
      const source = await this.read(this.identity.session(), generation);
      if (source === null) throw new EntryReadError('authentication_required');
      if (source.deployment !== this.deployment) throw new EntryReadError('invalid_response');
      const session = Object.freeze({...source, context: Object.freeze({...source.context})});
      this.clock.anchor(session.serverTime); this.ensureTime(session);
      if (!session.householdApiAvailable) {this.update({...blank('ready'), session, notice: 'api_unavailable'}); return true;}
      const access = await this.read(this.server.authorization(session.context), generation);
      if (access.state !== 'active') {this.update({...blank('ready'), session, access, notice: 'inactive'}); return true;}
      if (access.member === null) throw new EntryReadError('invalid_response');
      const capabilities = await this.read(this.server.capabilities(session.context), generation);
      const facts: Facts = {household: null, roster: null, policy: null, directory: null, preferences: null};
      const errors: Partial<Record<keyof Facts, ReadFault>> = {};
      const collect = async <K extends keyof Facts>(key: K, factory: () => EntryRead<Facts[K]>): Promise<void> => {
        try {facts[key] = await this.read(factory(), generation);}
        catch (error) {if (generation !== this.generation) throw retired; errors[key] = fault(error);}
      };
      const has = (permission: string) => access.permissions.includes(permission);
      await Promise.all([
        has('household.read') ? collect('household', () => this.server.household(session.context)) : undefined,
        has('members.read') ? collect('roster', () => this.server.roster(session.context)) : undefined,
        has('policy.manage') ? collect('policy', () => this.server.policy(session.context)) : undefined,
        has('policy.manage') ? collect('directory', () => this.server.directory(session.context)) : undefined,
        has('preferences.read') ? collect('preferences', () => this.server.preferences(session.context)) : undefined,
      ]);
      if (facts.preferences !== null && facts.preferences.memberId !== access.member.memberId) {
        facts.preferences = null; errors.preferences = 'invalid_response';
      }
      if (facts.policy !== null && facts.household !== null && facts.policy.householdId !== facts.household.householdId) {
        facts.policy = null; errors.policy = 'invalid_response';
      }
      const current = await this.read(this.server.authorization(session.context), generation);
      const now = this.ensureTime(session);
      if (JSON.stringify(current) !== JSON.stringify(access)) {
        this.retained = null; this.update({...blank('ready'), session, access: current, notice: 'access_changed'}); return true;
      }
      let notice: AdministrationNotice | null = session.access === 'read_only' ? 'read_only' : null;
      if (session.access === 'full') {
        try {
          const opened = this.journal.open(session.context, now);
          if (!sameContext(opened.context, session.context)) throw new Error();
          this.opened = opened;
        } catch {this.journal.detach(); this.opened = null; notice = 'journal_unavailable';}
      }
      if (this.retained !== null && (!sameContext(this.retained.context, session.context)
          || now >= this.retained.request.expiresAt || session.access !== 'full' || !allowed(access, this.retained.request)
          || (this.retained.outcome.kind === 'receipt' && !this.bound(this.retained.outcome, this.retained.request, access, facts))))
        this.retained = null;
      const retained = this.retained;
      this.update({phase: 'ready', session, access, capabilities, ...facts, errors: Object.freeze(errors),
        journal: this.opened === null ? null : this.visible(this.opened, access),
        outcome: retained === null ? null : retained.outcome, notice: notice ?? retained?.notice ?? null});
      return true;
    } catch (error) {
      if (generation !== this.generation) return false;
      this.block(fault(error)); return false;
    }
  }
  async refresh(): Promise<void> {if (this.state.phase !== 'closed') await this.load(this.begin());}
  /** Composition supplies monotonic ticks; this never refreshes or extends a session. */
  tick(): void {
    const session = this.state.session; if (session === null) return;
    let now: number;
    try {now = this.ensureTime(session); if (this.opened !== null && now < this.opened.observedAt) throw new Error();}
    catch {this.block('authentication_required'); return;}
    if (this.opened !== null) this.showJournal(Object.freeze({...this.opened,
      records: Object.freeze(this.opened.records.filter(record => now < record.expiresAt))}));
    if (this.retained !== null && now >= this.retained.request.expiresAt) {
      this.retained = null; this.update({outcome: null});
    }
  }
  private context(): JournalContext | null {
    this.tick();
    return this.running || this.state.phase !== 'ready' || this.state.session === null
      || this.state.session.access !== 'full' || this.state.access?.state !== 'active' || this.opened === null
      ? null : this.state.session.context;
  }
  private revision(command: AdministrationCommand): Revision | null {
    switch (command.action) {
      case 'household.update': return this.state.household?.revision ?? null;
      case 'member.update': return this.state.roster?.members.find(row => row.member.memberId === command.memberId)?.member.revision ?? null;
      case 'policy.update': return this.state.policy?.revision ?? null;
      case 'member.presentation.update': return this.state.roster?.members.find(row => row.member.memberId === command.memberId)?.presentation.revision ?? null;
      case 'member.preferences.update': return this.state.preferences?.revision ?? null;
    }
  }
  private bound(receipt: AdministrationReceipt, request: AdministrationRecord, access: AdministrationAccess, facts: Facts): boolean {
    if (receipt.action !== request.action || (request.operationId !== null && receipt.operationId !== request.operationId)) return false;
    if (request.action === 'member.preferences.update')
      return 'memberId' in receipt.result && receipt.result.memberId === access.member!.memberId;
    if (request.action === 'household.update' || request.action === 'policy.update') {
      const home = request.action === 'household.update' ? facts.household : facts.policy;
      return 'householdId' in receipt.result && (home === null || receipt.result.householdId === home.householdId);
    }
    return true;
  }
  async submit(value: unknown): Promise<void> {
    if (this.running || this.state.phase === 'closed') return;
    let command: AdministrationCommand;
    try {command = administrationCommand(value);} catch {this.update({notice: 'invalid_input'}); return;}
    await this.run({kind: 'new', command});
  }
  recover(key: string): Promise<void> {return this.run({kind: 'recover', key});}
  dismiss(key: string): Promise<void> {return this.run({kind: 'dismiss', key});}
  private async run(intent: Intent): Promise<void> {
    const context = this.context(); if (context === null) return;
    const original = intent.kind === 'new' ? null : this.opened!.records.find(record => record.key === intent.key);
    if (original === undefined) {this.update({notice: 'request_unavailable'}); return;}
    this.running = true;
    const generation = this.begin();
    try {
      if (!await this.load(generation) || generation !== this.generation) return;
      if (this.state.session === null || !sameContext(context, this.state.session.context)) {this.update({notice: 'context_changed'}); return;}
      const access = this.state.access;
      if (this.state.session.access !== 'full' || access?.state !== 'active' || this.opened === null) return;
      let request: AdministrationRecord;
      if (intent.kind === 'new') {
        if (!allowed(access, intent.command)) {this.update({notice: 'action_not_allowed'}); return;}
        const revision = this.revision(intent.command);
        if (revision === null) {this.update({notice: 'action_not_allowed'}); return;}
        if (revision !== intent.command.payload.expected_revision) {this.update({notice: 'conflict'}); return;}
        try {nextRevision(revision);} catch {this.update({notice: 'revision_exhausted'}); return;}
        if (this.opened.records.some(record => (record.stage === 'prepared' || record.stage === 'uncertain')
            && sameAggregate(record, intent.command))) {this.update({notice: 'previous_request_unresolved'}); return;}
        this.showJournal(this.journal.prepare(this.entropy.requestKey(), intent.command, this.clock.now()));
        request = this.opened!.records[this.opened!.records.length - 1];
      } else {
        const found = this.opened.records.find(record => record.key === intent.key);
        if (found === undefined) {this.update({notice: 'request_unavailable'}); return;}
        if (JSON.stringify(found) !== JSON.stringify(original)) {this.update({notice: 'request_changed'}); return;}
        request = found;
        if (!allowed(access, request)) {this.update({notice: 'action_not_allowed'}); return;}
        if (intent.kind === 'dismiss') {
          if (request.stage === 'prepared' || request.stage === 'uncertain') {this.update({notice: 'previous_request_unresolved'}); return;}
          this.showJournal(this.journal.forget(request.key, this.clock.now()));
          if (this.retained?.request.key === request.key) {this.retained = null; this.update({outcome: null});}
          return;
        }
        if (request.stage === 'rejected' || !access.permissions.includes('operations.read')) {this.update({notice: 'action_not_allowed'}); return;}
      }
      this.tick(); if (generation !== this.generation) return;
      this.update({phase: 'sending', notice: null});
      let outcome: AdministrationCommandResult;
      const command = commandOf(request);
      if (intent.kind === 'new') {
        try {outcome = await this.server.send({key: request.key, command}, context);}
        catch {outcome = Object.freeze({kind: 'uncertain'});}
      } else {
        const input: AdministrationOriginal = Object.freeze({key: request.key, command, operationId: request.operationId});
        try {outcome = await this.read(request.operationId === null ? this.server.original(input, context)
          : this.server.operation(input, context), generation);}
        catch (error) {
          if (generation !== this.generation) return;
          const reason = fault(error);
          if (reason === 'authentication_required' || reason === 'forbidden') this.block(reason);
          else this.update({phase: 'ready', notice: reason === 'invalid_response' ? reason : 'check_unconfirmed'});
          return;
        }
      }
      if (generation !== this.generation) return;
      this.tick(); if (generation !== this.generation) return;
      let notice: AdministrationNotice | null = null;
      if (outcome.kind === 'receipt' && !this.bound(outcome, request, access, this.state)) {
        if (intent.kind !== 'new') {this.update({phase: 'ready', notice: 'invalid_response'}); return;}
        outcome = Object.freeze({kind: 'uncertain'}); notice = 'invalid_response';
      }
      try {this.showJournal(this.journal.record(request.key, {stage: outcome.kind === 'receipt' ? outcome.stage
        : outcome.kind === 'rejected' ? 'rejected' : 'uncertain', operationId: outcome.kind === 'receipt' ? outcome.operationId : null}, this.clock.now()));}
      catch {this.journal.detach(); this.opened = null; this.update({journal: null}); notice = 'journal_unavailable';}
      this.retained = Object.freeze({context, request, outcome, notice}); this.update({outcome, notice});
      if (outcome.kind === 'rejected' && (outcome.reason === 'authentication_required' || outcome.reason === 'forbidden')) {
        this.block(outcome.reason); this.update({outcome}); return;
      }
      await this.load(this.begin());
    } catch {if (generation === this.generation) {
      this.journal.detach(); this.opened = null; this.update({phase: 'ready', journal: null, notice: 'journal_unavailable'});
    }} finally {this.running = false;}
  }
  close(): void {this.invalidate(); this.retained = null; this.state = blank('closed');}
}
