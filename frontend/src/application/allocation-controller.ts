/** Binds allocation operations to the verified member, selected work, and original request. */
import type {Revision} from '../domain/administration';
import type {JournalContext} from '../domain/journal';
import type {AllocationInput, AllocationPolicy, AllocationPreview, AllocationSettings, PolicyRevision, ReviewedAllocation} from '../domain/point-allocation';
import type {EntryEntropy, EntryRead} from './ports';

export interface AllocationWork {
  readonly occurrenceId: string;
  readonly revision: Revision;
  readonly canComplete: boolean;
}
export interface AllocationScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly definitionId: string | null;
  readonly work: AllocationWork | null;
  readonly canManage: boolean;
  readonly readOnly: boolean;
}
export interface AllocationRequest {
  readonly key: string;
  readonly scope: string;
  readonly definitionId: string | null;
  readonly revision: PolicyRevision;
  readonly policy: AllocationPolicy | null;
}
export type AllocationOutcome = 'saved' | 'historical' | 'rejected';
export interface AllocationServer {
  settings(scope: AllocationScope): EntryRead<AllocationSettings>;
  preview(scope: AllocationScope, work: AllocationWork, draft: AllocationInput): EntryRead<AllocationPreview | 'precisionRequired' | null>;
  save(scope: AllocationScope, request: AllocationRequest): EntryRead<AllocationOutcome>;
  original(scope: AllocationScope, request: AllocationRequest): EntryRead<AllocationOutcome | null>;
}
export interface AllocationJournal {
  open(scope: string): AllocationRequest | null;
  save(request: AllocationRequest): void;
  clear(request: AllocationRequest): void;
}
export interface AllocationReview {
  readonly evidence: AllocationPreview;
  readonly completion: ReviewedAllocation;
}
export interface AllocationView {
  readonly scope: AllocationScope;
  readonly settings: AllocationSettings | null;
  readonly review: AllocationReview | null;
  readonly pending: boolean;
  readonly busy: boolean;
  readonly notice: AllocationOutcome | 'uncertain' | 'unavailable' | 'precisionRequired' | null;
}
const INITIAL = {settings: null, review: null, pending: false, busy: false, notice: null} as const;

export class AllocationController {
  private state: AllocationView | null = null;
  private owned: EntryRead<unknown> | null = null;
  private request: AllocationRequest | null = null;

  constructor(private readonly server: AllocationServer, private readonly journal: AllocationJournal,
    private readonly entropy: EntryEntropy, private readonly publish: (value: AllocationView | null) => void) {}

  bind(scope: AllocationScope | null): void {
    const previous = this.state?.scope;
    if (previous?.key === scope?.key && previous?.definitionId === scope?.definitionId
        && previous?.work?.occurrenceId === scope?.work?.occurrenceId && previous?.work?.revision === scope?.work?.revision
        && previous?.work?.canComplete === scope?.work?.canComplete
        && previous?.canManage === scope?.canManage && previous?.readOnly === scope?.readOnly) return;
    this.owned?.cancel(); this.owned = null; this.request = null;
    this.state = scope === null ? null : {...INITIAL, scope};
    this.publish(this.state);
    if (scope?.canManage) {
      try {this.request = this.journal.open(scope.key); this.set({pending: this.request !== null});}
      catch {this.set({pending: true, notice: 'unavailable'});}
      void this.refresh();
    }
  }

  private set(patch: Partial<AllocationView>): void {
    this.state = {...this.state!, ...patch}; this.publish(this.state);
  }

  async refresh(): Promise<void> {
    const scope = this.state?.scope;
    if (!scope?.canManage || this.owned !== null) return;
    const loaded = await this.run(this.server.settings(scope), settings => this.set({settings}), 'unavailable');
    if (!loaded && this.state?.scope === scope) this.set({settings: null});
  }

  async preview(draft: AllocationInput): Promise<void> {
    const scope = this.state?.scope, work = scope?.work;
    if (!scope || !work?.canComplete || scope.readOnly || this.owned !== null
        || (draft.manualShares !== undefined && !scope.canManage)) return;
    this.set({review: null, notice: null});
    await this.run(this.server.preview(scope, work, draft), evidence => {
      if (evidence === null || evidence === 'precisionRequired') {
        this.set({notice: evidence ?? 'rejected'}); return;
      }
      this.set({review: {evidence, completion: {...draft, occurrenceId: work.occurrenceId,
        revision: work.revision, fingerprint: evidence.fingerprint}}});
    }, 'unavailable');
  }

  async save(policy: AllocationPolicy | null): Promise<void> {
    const state = this.state;
    if (!state?.scope.canManage || state.scope.readOnly || state.pending || state.settings === null
        || this.owned !== null || (state.scope.definitionId === null && policy === null)) return;
    const {scope, settings} = state;
    const setting = scope.definitionId === null ? settings.household : settings.override;
    let request: AllocationRequest;
    try {
      request = {key: this.entropy.requestKey(), scope: scope.key, definitionId: scope.definitionId,
        revision: setting?.revision ?? '0', policy};
      this.journal.save(request);
    } catch {this.set({notice: 'unavailable'}); return;}
    this.request = request;
    this.set({pending: true, notice: null, review: null});
    await this.settle(this.server.save(scope, request), request);
  }

  async recover(): Promise<void> {
    const scope = this.state?.scope, request = this.request;
    if (!scope?.canManage || request === null || this.owned !== null) return;
    const result = await this.run(this.server.original(scope, request), outcome => {
      if (outcome !== null) this.finish(request, outcome);
    }, 'uncertain');
    if (result && this.state?.scope === scope) {
      if (this.request === null) await this.refresh();
      else if (!scope.readOnly) await this.settle(this.server.save(scope, request), request);
    }
  }

  private async settle(owned: EntryRead<AllocationOutcome>, request: AllocationRequest): Promise<void> {
    if (await this.run(owned, outcome => this.finish(request, outcome), 'uncertain')) await this.refresh();
  }

  private finish(request: AllocationRequest, outcome: AllocationOutcome): void {
    this.journal.clear(request); this.request = null;
    this.set({pending: false, notice: outcome});
  }

  private async run<T>(owned: EntryRead<T>, use: (result: T) => void,
    notice: 'uncertain' | 'unavailable'): Promise<boolean> {
    this.owned = owned; this.set({busy: true});
    try {
      const value = await owned.result;
      if (this.owned !== owned) return false;
      use(value); return true;
    } catch {
      if (this.owned === owned) this.set({notice});
      return false;
    } finally {
      if (this.owned === owned) {this.owned = null; this.set({busy: false});}
    }
  }
}
