/** Reviews bind to current task facts and recover only the saved original request. */
import {EntryReadError} from './ports';
import type {EntryClock, EntryEntropy, EntryRead} from './ports';
import {JOURNAL_LIFETIME} from '../domain/journal';
import type {JournalContext} from '../domain/journal';
import {reviewSelection} from '../domain/recurrence-review';
import type {ReviewCommand, ReviewDraft, ReviewTarget} from '../domain/recurrence-review';

export interface ReviewRecord {
  readonly key: string; readonly command: ReviewCommand; readonly createdAt: number;
  readonly status: 'pending' | 'received'; readonly operationId: string | null;
}
export interface ReviewJournal {
  open(scope: string, now: number): readonly ReviewRecord[];
  save(scope: string, now: number, records: readonly ReviewRecord[]): readonly ReviewRecord[];
  detach(): void;
}
export interface ReviewScope {
  readonly key: string; readonly context: JournalContext; readonly occurrenceId: string | null;
  readonly readOnly: boolean; readonly serverTime: number; readonly expiresAt: number;
}
export interface ReviewPreview {
  readonly fingerprint: string; readonly expiresAt: number;
  readonly retained: number | null; readonly planned: number | null;
  readonly previous: string | null; readonly destination: string | null;
  readonly createsFirst: boolean | null;
}
export interface ReviewReceipt {
  readonly operationId: string; readonly historical: boolean; readonly preview: ReviewPreview | null;
}
export interface ReviewServer {
  target(context: JournalContext, occurrenceId: string): EntryRead<ReviewTarget>;
  send(context: JournalContext, request: ReviewRecord): EntryRead<ReviewReceipt>;
  original(context: JournalContext, request: ReviewRecord): EntryRead<ReviewReceipt>;
}
export type ReviewNotice = 'invalid' | 'unavailable' | 'uncertain' | 'expired' | 'rejected' | 'journal';
export interface ReviewView {
  readonly open: boolean; readonly busy: boolean; readonly readOnly: boolean;
  readonly selected: boolean; readonly target: ReviewTarget | null; readonly records: readonly ReviewRecord[];
  readonly result: Readonly<{record: ReviewRecord; receipt: ReviewReceipt}> | null;
  readonly notice: ReviewNotice | null;
}
const EMPTY: ReviewView = Object.freeze({open: false, busy: false, readOnly: true, selected: false,
  target: null, records: [], result: null, notice: null});

export class RecurrenceReviewController {
  private scope: ReviewScope | null = null;
  private state = EMPTY;
  private pending: EntryRead<unknown> | null = null;
  private journalAvailable = false;
  constructor(private readonly server: ReviewServer, private readonly journal: ReviewJournal,
    private readonly clock: EntryClock, private readonly entropy: EntryEntropy,
    private readonly publish: (value: ReviewView | null) => void) {}

  bind(scope: ReviewScope | null): void {
    const previous = this.scope;
    this.scope = scope;
    if (scope === null) {
      if (previous !== null) {
        this.cancel(); this.journal.detach(); this.journalAvailable = false; this.state = EMPTY; this.publish(null);
      }
      return;
    }
    if (previous?.serverTime !== scope.serverTime) this.clock.anchor(scope.serverTime);
    if (previous?.key !== scope.key) {
      this.cancel(); this.journal.detach();
      this.state = {...EMPTY, readOnly: scope.readOnly, selected: scope.occurrenceId !== null};
      try {this.journalAvailable = true; this.set({records: this.journal.open(scope.key, this.clock.now())});}
      catch {this.journalAvailable = false; this.set({notice: 'journal'});}
    } else if (previous.occurrenceId !== scope.occurrenceId || previous.readOnly !== scope.readOnly) {
      this.cancel(); this.set({open: false, busy: false, readOnly: scope.readOnly, selected: scope.occurrenceId !== null, target: null, result: null});
    } else {
      const now = this.clock.now();
      const preview = this.state.result?.receipt.preview;
      if (preview && now >= preview.expiresAt) this.set({result: null, notice: 'expired'});
      if (!this.state.busy && this.journalAvailable && this.state.records.some(item => now - item.createdAt >= JOURNAL_LIFETIME)) {
        try {this.persist(scope, this.state.records);}
        catch {this.journalAvailable = false; this.set({notice: 'journal'});}
      }
    }
  }

  private cancel(): void {this.pending?.cancel(); this.pending = null;}
  private set(patch: Partial<ReviewView>): void {
    this.state = Object.freeze({...this.state, ...patch}); this.publish(this.state);
  }
  private current(): ReviewScope | null {
    return this.scope !== null && !this.state.busy && this.clock.now() < this.scope.expiresAt ? this.scope : null;
  }
  close(): void {
    if (this.scope === null || this.state.busy) return;
    this.set({open: false, target: null, result: null, notice: null});
  }
  async open(): Promise<void> {
    const scope = this.current();
    if (scope === null) return;
    this.set({open: true, result: null, notice: null});
    if (scope.occurrenceId === null) return;
    await this.run(this.server.target(scope.context, scope.occurrenceId), value => this.set({target: value}), () => 'unavailable');
  }
  async preview(draft: ReviewDraft): Promise<void> {
    const scope = this.current(), target = this.state.target;
    if (scope === null || scope.readOnly || target === null || !this.journalAvailable) return;
    let command: ReviewCommand;
    try {command = {step: 'preview', selection: reviewSelection(target, draft)};}
    catch {this.set({notice: 'invalid', result: null}); return;}
    await this.submit(scope, command);
  }
  async apply(): Promise<void> {
    const scope = this.current(), outcome = this.state.result;
    if (scope === null || scope.readOnly || outcome === null || !this.journalAvailable) return;
    const {receipt, record} = outcome;
    if (receipt.preview === null || receipt.historical || this.clock.now() >= receipt.preview.expiresAt) {
      this.set({notice: 'expired', result: null}); return;
    }
    if (this.state.records.some(item => item.command.step === 'apply' && item.command.previewKey === record.key)) {
      this.set({notice: 'uncertain'}); return;
    }
    await this.submit(scope, {step: 'apply', selection: record.command.selection, previewKey: record.key, fingerprint: receipt.preview.fingerprint});
  }
  private async submit(scope: ReviewScope, command: ReviewCommand): Promise<void> {
    if (this.state.records.some(item => item.status === 'pending')) {this.set({notice: 'uncertain'}); return;}
    let record: ReviewRecord;
    try {
      record = {key: this.entropy.requestKey(), command, createdAt: this.clock.now(), status: 'pending', operationId: null};
      this.persist(scope, [...this.state.records, record]);
    } catch {this.set({notice: 'journal'}); return;}
    await this.receive(scope, record, true);
  }
  private persist(scope: ReviewScope, records: readonly ReviewRecord[]): void {
    this.set({records: this.journal.save(scope.key, this.clock.now(), records)});
  }
  async recover(key: string): Promise<void> {
    const scope = this.current(), record = this.state.records.find(item => item.key === key);
    if (scope === null || record === undefined) return;
    this.set({open: true}); await this.receive(scope, record, false);
  }
  forget(key: string): void {
    const scope = this.current(), record = this.state.records.find(item => item.key === key);
    if (scope === null || record?.status !== 'received') return;
    try {
      this.persist(scope, this.state.records.filter(item => item.key !== record.key));
      if (this.state.result?.record.key === key) this.set({result: null});
    } catch {this.set({notice: 'journal'});}
  }
  private async receive(scope: ReviewScope, record: ReviewRecord, send: boolean): Promise<void> {
    this.set({result: null, notice: null});
    const request = send ? this.server.send(scope.context, record) : this.server.original(scope.context, record);
    await this.run(request, receipt => {
      if (record.operationId !== null && record.operationId !== receipt.operationId) throw new EntryReadError('invalid_response');
      const updated: ReviewRecord = {...record, status: 'received', operationId: receipt.operationId};
      try {this.persist(scope, this.state.records.map(item => item.key === updated.key ? updated : item));}
      catch {this.set({notice: 'journal'}); return;}
      this.set({result: {record: updated, receipt}});
    }, error => {
      if (send && error instanceof ReviewRejected) {
        try {this.persist(scope, this.state.records.filter(item => item.key !== record.key));}
        catch {return 'journal';}
        return 'rejected';
      }
      return 'uncertain';
    });
  }
  private async run<T>(request: EntryRead<T>, completed: (value: T) => void, failure: (error: unknown) => ReviewNotice): Promise<void> {
    this.pending = request; this.set({busy: true});
    try {
      const value = await request.result;
      if (this.pending === request && this.scope !== null && this.clock.now() < this.scope.expiresAt) completed(value);
    } catch (error) {
      if (this.pending === request) this.set({notice: failure(error)});
    } finally {
      if (this.pending === request) {this.pending = null; this.set({busy: false});}
    }
  }
}

export class ReviewRejected extends Error {}
