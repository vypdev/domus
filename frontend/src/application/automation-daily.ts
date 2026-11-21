/** Explicit, revision-bound grants; a lost reply never becomes a replacement request. */
import type {Revision} from '../domain/administration';
import type {DraftCondition, DraftScope} from './automation-drafts';
import type {DAILY_RESOLUTIONS} from './automation-schedule-preview';
import {EntryReadError} from './ports';
import type {EntryEntropy, EntryRead} from './ports';

export interface DailyPolicy {
  readonly zone: string;
  readonly dataIdentity: string;
  readonly repeatedTime: 'first_instant' | 'second_instant';
  readonly revision: Revision;
}
export interface ReviewedDailyTime {
  readonly nominal: string;
  readonly policy: DailyPolicy;
  readonly resolvedLocal: string;
  readonly offsetSeconds: number;
  readonly resolution: typeof DAILY_RESOLUTIONS[number];
  readonly zoneDigest: string;
}
export function dailyInstant(value: ReviewedDailyTime): number {
  return Date.parse(value.resolvedLocal + 'Z') - value.offsetSeconds * 1000;
}
export interface DailyReview {
  readonly ruleId: string;
  readonly ruleRevision: Revision;
  readonly title: string;
  readonly requestedTime: string;
  readonly controlRevision: Revision | '0';
  readonly scheduleRevision: Revision | '0';
  readonly enabled: boolean;
  readonly activeTrigger: 'manual' | 'daily' | null;
  readonly activeRevision: Revision | null;
  readonly activeTitle: string | null;
  readonly conditionProducts: readonly string[];
  readonly condition: DraftCondition | null;
  readonly mayEnable: boolean;
  readonly approvedPolicy: DailyPolicy | null;
  readonly proposedPolicy: DailyPolicy;
  readonly approvedTimes: readonly ReviewedDailyTime[] | null;
  readonly proposedTimes: readonly ReviewedDailyTime[];
  readonly proposedUnavailable: boolean;
  readonly approvedUnavailable: boolean;
  readonly policyChanged: boolean;
  readonly next: ReviewedDailyTime | null;
  readonly suppression: Readonly<{first: ReviewedDailyTime; throughMs: number}> | null;
}
export type DailyAction = 'enable' | 'disable' | 'adopt';
export type DailyCommand = Readonly<{kind: DailyAction; ruleId: string; ruleRevision: Revision;
  controlRevision: Revision | '0'; scheduleRevision: Revision | '0'; reviewed?: ReviewedDailyTime}>;
export type DailyRequest = DailyCommand & Readonly<{key: string; scope: string}>;
export interface DailyResult {
  readonly kind: 'committed' | 'historical';
  readonly action: DailyAction;
  readonly ruleId: string;
  readonly ruleRevision: Revision;
  readonly operationId: string;
  readonly next: ReviewedDailyTime;
}
export type DailyOutcome = DailyResult | Readonly<{kind: 'missing' | 'stale' | 'timing_changed' | 'disabled' | 'rejected'}>;
export interface DailyServer {
  active(scope: DraftScope, ruleId: string): EntryRead<DailyReview | null>;
  review(scope: DraftScope, ruleId: string, revision: Revision): EntryRead<DailyReview>;
  send(scope: DraftScope, request: DailyRequest): EntryRead<DailyOutcome>;
  original(scope: DraftScope, request: DailyRequest): EntryRead<DailyOutcome>;
}
export interface DailyJournal {
  open(scope: string): DailyRequest | null;
  save(request: DailyRequest): void;
  clear(request: DailyRequest): void;
}
export interface DailyScope extends DraftScope {readonly authorization: string; readonly timing: string;}
export interface DailySelection {
  readonly id: string;
  readonly revision: Revision;
  readonly dailyTime?: string;
  readonly activeDaily?: Revision;
}
export type DailyIntent = DailyAction | 'active' | 'saved' | 'reload' | 'confirm' | 'cancel' | 'recover';
type Notice = 'unavailable' | 'denied' | 'uncertain' | 'journal_unavailable' | 'record_failed' | 'stale' | 'timing_changed' | 'disabled' | 'rejected';
export interface DailyView {
  readonly review: DailyReview | null;
  readonly confirmation: DailyCommand | null;
  readonly result: DailyResult | null;
  readonly notice: Notice | null;
  readonly busy: boolean;
  readonly pending: boolean;
  readonly readOnly: boolean;
  readonly savedRevision: Revision | null;
}

export class DailyAutomationController {
  private scope: DailyScope | null = null;
  private selection: DailySelection | null = null;
  private review: DailyReview | null = null;
  private confirmation: DailyCommand | null = null;
  private result: DailyResult | null = null;
  private notice: Notice | null = null;
  private pending: DailyRequest | null = null;
  private owned: EntryRead<unknown> | null = null;
  private generation = 0;

  constructor(private readonly server: DailyServer, private readonly journal: DailyJournal,
    private readonly entropy: EntryEntropy, private readonly publish: (view: DailyView | null) => void,
    private readonly changed: () => void) {}

  bind(scope: DailyScope | null, selection: DailySelection | null): void {
    const prior = this.scope, before = this.selection;
    this.scope = scope;
    this.selection = selection;
    const sameOwner = prior?.key === scope?.key;
    const sameAuthority = prior?.authorization === scope?.authorization && prior?.timing === scope?.timing;
    const sameSelection = before?.id === selection?.id && before?.revision === selection?.revision
      && before?.dailyTime === selection?.dailyTime;
    const activeChanged = before?.activeDaily !== selection?.activeDaily;
    if (sameOwner && sameAuthority && sameSelection && !activeChanged) {this.emit(); return;}
    this.generation++;
    this.owned?.cancel();
    this.owned = null;
    this.review = null;
    this.confirmation = null;
    if (!sameOwner || prior?.authorization !== scope?.authorization || (!sameSelection && this.pending === null)) this.result = null;
    this.notice = sameOwner && this.pending !== null ? 'uncertain' : null;
    if (!sameOwner) {
      this.pending = null;
      if (scope !== null) {
        try {this.pending = this.journal.open(scope.key);}
        catch {this.notice = 'journal_unavailable';}
        if (this.pending !== null) this.notice = 'uncertain';
      }
    }
    if (scope !== null) void this.load(scope);
    else this.emit();
  }

  private target(): Readonly<{id: string; revision: Revision | null}> | null {
    if (this.pending !== null) return {id: this.pending.ruleId, revision: this.pending.ruleRevision};
    const selected = this.selection;
    if (selected === null) return this.result === null ? null : {id: this.result.ruleId, revision: this.result.ruleRevision};
    return {id: selected.id, revision: selected.dailyTime === undefined ? null : selected.revision};
  }

  private emit(): void {
    const noDailyFacts = this.selection?.dailyTime === undefined && this.review === null && this.pending === null
      && this.result === null && this.notice === null;
    this.publish(this.scope === null || ((this.target() === null || noDailyFacts) && this.result === null) ? null : {
      review: this.review, confirmation: this.confirmation, result: this.result, notice: this.notice,
      busy: this.owned !== null, pending: this.pending !== null, readOnly: this.scope.readOnly,
      savedRevision: this.selection?.dailyTime === undefined ? null : this.selection.revision,
    });
  }

  private retire(): void {
    this.review = null;
    this.confirmation = null;
    this.result = null;
    if (this.pending !== null) {
      try {this.journal.clear(this.pending);} catch {/* Rejected private facts cannot be exposed by local storage. */}
    }
    this.pending = null;
    this.notice = 'denied';
  }

  private async own<T>(request: EntryRead<T>, accept: (value: T) => void, fail: () => void): Promise<void> {
    this.owned = request;
    this.emit();
    try {
      const value = await request.result;
      if (this.owned === request) accept(value);
    } catch (error) {
      if (this.owned !== request) return;
      if (error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required'))
        this.retire();
      else fail();
    } finally {
      if (this.owned === request) {this.owned = null; this.emit();}
    }
  }

  private async load(scope: DailyScope, target = this.target()): Promise<void> {
    this.confirmation = null;
    if (target === null) {this.review = null; this.emit(); return;}
    const request = target.revision === null ? this.server.active(scope, target.id)
      : this.server.review(scope, target.id, target.revision);
    await this.own(request, value => {this.review = value;}, () => {
      this.review = null;
      if (this.pending === null) this.notice = 'unavailable';
    });
  }

  private prepare(kind: DailyAction): void {
    const review = this.review;
    if (review === null) return;
    const active = review.enabled && review.activeTrigger === 'daily' && review.activeRevision !== null;
    if (kind !== 'disable' && review.proposedUnavailable) return;
    if (kind === 'enable' && (!review.mayEnable || (active && review.activeRevision === review.ruleRevision))) return;
    if (kind !== 'enable' && !active) return;
    if (kind === 'adopt' && (!review.policyChanged || review.activeRevision !== review.ruleRevision)) return;
    this.confirmation = {kind, ruleId: review.ruleId,
      ruleRevision: kind === 'disable' ? review.activeRevision! : review.ruleRevision,
      controlRevision: review.controlRevision, scheduleRevision: review.scheduleRevision,
      ...(kind === 'disable' ? {} : {reviewed: review.proposedTimes[0]})};
    this.emit();
  }

  async handle(intent: DailyIntent): Promise<void> {
    const scope = this.scope;
    if (scope === null || this.owned !== null) return;
    if (intent === 'cancel') {this.confirmation = null; this.emit(); return;}
    if (intent === 'reload') {this.notice = null; await this.load(scope); return;}
    if (intent === 'recover') {await this.recover(scope); return;}
    if (this.pending !== null) return;
    if (intent === 'active' && this.review?.activeTrigger === 'daily' && this.review.activeRevision !== null) {
      await this.load(scope, {id: this.review.ruleId, revision: this.review.activeRevision}); return;
    }
    if (intent === 'saved') {await this.load(scope); return;}
    if (scope.readOnly) return;
    if (intent !== 'confirm') {if (intent !== 'active') this.prepare(intent); return;}
    const confirmation = this.confirmation;
    if (confirmation === null) return;
    let request: DailyRequest;
    try {
      request = {...confirmation, key: this.entropy.requestKey(), scope: scope.key};
      this.journal.save(request);
    } catch {this.notice = 'record_failed'; this.emit(); return;}
    this.pending = request;
    this.review = null;
    this.confirmation = null;
    this.result = null;
    this.notice = null;
    await this.complete(scope, request, this.server.send(scope, request));
  }

  private async recover(scope: DailyScope): Promise<void> {
    const request = this.pending, generation = this.generation;
    if (request === null) return;
    const missing = await this.complete(scope, request, this.server.original(scope, request));
    if (missing && generation === this.generation && this.pending === request && !this.scope!.readOnly)
      await this.complete(this.scope!, request, this.server.send(this.scope!, request));
  }

  private async complete(scope: DailyScope, request: DailyRequest, transport: EntryRead<DailyOutcome>): Promise<boolean> {
    let missing = false, refresh = false;
    const generation = this.generation;
    await this.own(transport, value => {
      if (value.kind === 'missing') {missing = true; this.notice = 'uncertain'; return;}
      if ('action' in value) {this.result = value; this.notice = null;}
      else this.notice = value.kind;
      try {this.journal.clear(request); this.pending = null;}
      catch {this.notice = 'journal_unavailable';}
      refresh = true;
    }, () => {this.notice = 'uncertain';});
    if (refresh && generation === this.generation) {
      await this.load(scope);
      if (generation === this.generation) this.changed();
    }
    return missing;
  }
}
