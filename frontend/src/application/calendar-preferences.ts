/** Current private display state and original-result recovery have independent lifetimes. */
import type {Revision} from '../domain/administration';
import type {WeekStart} from '../domain/calendar';
import type {JournalContext} from '../domain/journal';
import {JOURNAL_LIFETIME} from '../domain/journal';
import type {EntryClock, EntryEntropy, EntryRead} from './ports';

export interface CalendarPreference {readonly weekStart: WeekStart; readonly revision: Revision;}
export interface PreferenceRequest extends CalendarPreference {
  readonly key: string;
  readonly scope: string;
  readonly createdAt: number;
}
export interface PreferenceScope {
  readonly key: string; readonly context: JournalContext; readonly memberId: string;
  readonly serverTime: number; readonly expiresAt: number; readonly readOnly: boolean;
}
export interface CalendarPreferenceServer {
  read(scope: PreferenceScope): EntryRead<CalendarPreference>;
  send(scope: PreferenceScope, request: PreferenceRequest): EntryRead<boolean>;
  original(scope: PreferenceScope, request: PreferenceRequest): EntryRead<boolean>;
}
export interface CalendarPreferenceJournal {
  open(scope: string, now: number): PreferenceRequest | null;
  save(request: PreferenceRequest): void;
  clear(request: PreferenceRequest): void;
}
export interface CalendarPreferenceView {
  readonly value: CalendarPreference | null;
  readonly pending: boolean;
  readonly busy: boolean;
  readonly readOnly: boolean;
  readonly notice: 'preferenceUnavailable' | 'preferenceUncertain' | 'preferenceRejected' | null;
}
const EMPTY: CalendarPreferenceView = {value:null,pending:false,busy:false,readOnly:true,notice:null};

export class CalendarPreferenceController {
  private scope: PreferenceScope | null = null;
  private state = EMPTY;
  private owned: EntryRead<unknown> | null = null;
  private original: PreferenceRequest | null = null;
  private writableJournal = false;

  constructor(private readonly server: CalendarPreferenceServer, private readonly journal: CalendarPreferenceJournal,
    private readonly clock: EntryClock, private readonly entropy: EntryEntropy,
    private readonly publish: (view: CalendarPreferenceView | null) => void) {}

  bind(scope: PreferenceScope | null): void {
    const previous = this.scope;
    this.scope = scope;
    if (scope === null) {
      if (previous !== null) {
        this.owned?.cancel(); this.owned = null; this.original = null; this.state = EMPTY; this.publish(null);
      }
      return;
    }
    if (previous?.serverTime !== scope.serverTime) this.clock.anchor(scope.serverTime);
    if (previous?.key === scope.key) {
      if (previous.readOnly !== scope.readOnly) this.set({readOnly:scope.readOnly || !this.writableJournal});
      return;
    }
    this.owned?.cancel(); this.owned = null; this.state = EMPTY; this.original = null;
    try {
      this.original = this.journal.open(scope.key, this.clock.now()); this.writableJournal = true;
      this.set({readOnly:scope.readOnly,pending:this.original !== null});
    } catch {
      this.writableJournal = false;
      this.set({notice:'preferenceUnavailable'});
    }
    void this.refresh();
  }

  private set(patch: Partial<CalendarPreferenceView>): void {
    this.state = Object.freeze({...this.state,...patch}); this.publish(this.state);
  }

  private current(): PreferenceScope | null {
    return this.scope !== null && this.owned === null && this.clock.now() < this.scope.expiresAt ? this.scope : null;
  }

  async refresh(): Promise<void> {
    const scope = this.current();
    if (scope === null) return;
    await this.run(this.server.read(scope), value => {this.set({value});}, 'preferenceUnavailable');
  }

  async save(weekStart: WeekStart): Promise<void> {
    const scope = this.current(), value = this.state.value;
    if (scope === null || this.state.readOnly || this.original !== null || value === null || weekStart === value.weekStart) return;
    let request: PreferenceRequest;
    try {
      request = {key:this.entropy.requestKey(),scope:scope.key,createdAt:this.clock.now(),weekStart,revision:value.revision};
      this.journal.save(request);
    } catch {
      this.set({notice:'preferenceUnavailable'}); return;
    }
    this.original = request;
    this.set({pending:true,notice:null});
    if (await this.run(this.server.send(scope, request), committed => this.finish(request, committed), 'preferenceUncertain')) {
      await this.refresh();
    }
  }

  async recover(): Promise<void> {
    const scope = this.current(), request = this.original;
    if (scope === null || request === null) return;
    if (this.clock.now() - request.createdAt >= JOURNAL_LIFETIME) {
      try {this.finish(request, false);}
      catch {this.set({notice:'preferenceUnavailable'});}
      return;
    }
    if (await this.run(this.server.original(scope, request), committed => this.finish(request, committed), 'preferenceUncertain')) {
      await this.refresh();
    }
  }

  private finish(request: PreferenceRequest, committed: boolean): void {
    this.journal.clear(request);
    this.original = null;
    this.set({pending:false,notice:committed ? null : 'preferenceRejected'});
  }

  private async run<T>(owned: EntryRead<T>, use: (value: T) => void,
    failure: NonNullable<CalendarPreferenceView['notice']>): Promise<boolean> {
    this.owned = owned; this.set({busy:true});
    try {
      const value = await owned.result;
      if (this.owned !== owned) return false;
      use(value); return true;
    } catch {
      if (this.owned === owned) this.set({notice:failure});
      return false;
    } finally {
      if (this.owned === owned) {this.owned = null; this.set({busy:false});}
    }
  }
}
