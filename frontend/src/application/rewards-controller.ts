/** Current Family scope, original commands, and private reward views. */
import type {JournalContext} from '../domain/journal';
import {managementAction, rewardCommand} from '../domain/rewards';
import type {RedemptionStage, RewardCommand, RewardReport} from '../domain/rewards';
import type {EntryEntropy, EntryRead} from './ports';

export interface RewardsScope {
  readonly key: string;
  readonly context: JournalContext;
  readonly memberId: string;
  readonly readOnly: boolean;
}
export interface RewardRequest {readonly key: string; readonly scope: string; readonly command: RewardCommand;}
export const REWARD_ERRORS = ['permission_denied', 'revision_conflict', 'invalid_request', 'rewards_disabled',
  'reward_unavailable', 'insufficient_reward_points', 'reward_funding_hold', 'redemption_not_requested',
  'redemption_not_approved', 'redemption_closed', 'reward_catalog_capacity', 'reward_request_capacity'] as const;
export type RewardError = typeof REWARD_ERRORS[number] | 'rejected';
export type RewardResult = Readonly<{kind: 'committed' | 'historical'; stage: RedemptionStage | null}>
  | Readonly<{kind: 'rejected'; reason: RewardError}>;
export interface RewardsServer {
  read(scope: RewardsScope, cursor: string | null): EntryRead<RewardReport>;
  send(scope: RewardsScope, request: RewardRequest): EntryRead<RewardResult>;
  original(scope: RewardsScope, request: RewardRequest): EntryRead<RewardResult | null>;
}
export interface RewardsJournal {
  open(scope: string): RewardRequest | null;
  save(request: RewardRequest): void;
  clear(request: RewardRequest): void;
}
export interface RewardsView {
  readonly scope: RewardsScope;
  readonly report: RewardReport | null;
  readonly pending: boolean;
  readonly busy: boolean;
  readonly result: RewardResult | null;
  readonly notice: 'unavailable' | 'uncertain' | null;
}
const INITIAL = {report: null, pending: false, busy: false, result: null, notice: null} as const;

export class RewardsController {
  private view: RewardsView | null = null;
  private owned: EntryRead<unknown> | null = null;
  private request: RewardRequest | null = null;

  constructor(private readonly server: RewardsServer, private readonly journal: RewardsJournal,
    private readonly entropy: EntryEntropy, private readonly publish: (view: RewardsView | null) => void,
    private readonly balanceChanged: () => Promise<void>) {}

  bind(scope: RewardsScope | null): void {
    const previous = this.view?.scope;
    if (scope?.key === previous?.key && scope?.readOnly === previous?.readOnly) return;
    this.owned?.cancel(); this.owned = null; this.request = null;
    this.view = scope === null ? null : {...INITIAL, scope};
    this.publish(this.view);
    if (scope === null) return;
    try {
      this.request = this.journal.open(scope.key);
      this.set({pending: this.request !== null});
    } catch {this.set({pending: true, notice: 'unavailable'});}
    void this.refresh();
  }

  private set(patch: Partial<RewardsView>): void {
    this.view = {...this.view!, ...patch}; this.publish(this.view);
  }

  async refresh(): Promise<void> {await this.load(null);}
  async more(): Promise<void> {
    const cursor = this.view?.report?.cursor;
    if (cursor) await this.load(cursor);
  }
  private async load(cursor: string | null): Promise<void> {
    const state = this.view;
    if (state === null || this.owned !== null) return;
    const loaded = await this.run(this.server.read(state.scope, cursor), page => {
      this.set({report: cursor === null ? page : {...page, requests: [...state.report!.requests, ...page.requests]},
        notice: state.notice === 'unavailable' ? null : state.notice});
    }, 'unavailable');
    if (!loaded && this.view?.scope === state.scope) this.set({report: null});
  }

  async submit(value: unknown): Promise<void> {
    const state = this.view;
    if (state === null || state.scope.readOnly || state.pending || state.report === null || this.owned !== null) return;
    let request: RewardRequest;
    try {
      const command = rewardCommand(value);
      if (managementAction(command.action) && !state.report.mayManage) return;
      request = {key: this.entropy.requestKey(), scope: state.scope.key, command};
      this.journal.save(request);
    } catch {this.set({notice: 'unavailable'}); return;}
    this.request = request;
    this.set({pending: true, notice: null, result: null});
    await this.settle(this.server.send(state.scope, request), request);
  }

  async recover(): Promise<void> {
    const scope = this.view?.scope, request = this.request;
    if (!scope || request === null || this.owned !== null) return;
    const done = await this.run(this.server.original(scope, request), result => {
      if (result !== null) this.finish(request, result);
    }, 'uncertain');
    if (!done || this.view?.scope !== scope) return;
    if (this.request === null) await this.updatedBalances();
    else if (!scope.readOnly) await this.settle(this.server.send(scope, request), request);
  }

  private async settle(read: EntryRead<RewardResult>, request: RewardRequest): Promise<void> {
    if (await this.run(read, result => this.finish(request, result), 'uncertain')) await this.updatedBalances();
  }

  private finish(request: RewardRequest, result: RewardResult): void {
    this.journal.clear(request); this.request = null;
    this.set({pending: false, notice: null, result});
  }

  private async updatedBalances(): Promise<void> {
    await Promise.all([this.refresh(), this.balanceChanged()]);
  }

  private async run<T>(owned: EntryRead<T>, use: (value: T) => void, notice: 'unavailable' | 'uncertain'): Promise<boolean> {
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
