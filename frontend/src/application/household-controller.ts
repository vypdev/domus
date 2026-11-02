/** Coordinate verified application views; concrete document resources and command authority stay with their owners. */
import type {EntryController, EntryNotice, EntryView} from './entry-controller';
import type {AdministrationController, AdministrationView} from './administration-controller';
import type {JournalContext} from '../domain/journal';

function sameContext(left: JournalContext, right: JournalContext): boolean {
  return left.installationId === right.installationId && left.channel === right.channel && left.subject === right.subject;
}
function sameGrants(left: readonly string[], right: readonly string[]): boolean {
  return JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());
}

export class HouseholdController {
  private current: AdministrationController | null = null;
  private currentContext: JournalContext | null = null;
  private visible = false;
  private running = false;
  private closed = false;
  private generation = 0;
  private notice: EntryNotice | null = null;
  constructor(private readonly entry: EntryController, private readonly administrationFactory: () => AdministrationController) {}
  get view(): EntryView {
    const view = this.entry.view;
    return Object.freeze({...view, busy: this.running || view.busy || this.current?.view.busy === true,
      notice: this.notice ?? view.notice});
  }
  get administration(): AdministrationView | null {return this.visible ? this.current!.view : null;}
  /** Scheduling needs only absolute deadlines, never a command payload or a renewed proof. */
  get deadlines(): readonly number[] {
    return Object.freeze([this.entry.view, this.current?.view].flatMap(view => view === undefined ? [] : [
      ...view.session === null ? [] : [view.session.expiresAt],
      ...view.journal?.records.map(record => record.expiresAt) ?? [],
    ]));
  }
  private live(generation: number): boolean {return !this.closed && generation === this.generation;}
  private retire(): void {
    this.visible = false; this.current?.close(); this.current = null; this.currentContext = null;
  }
  private eligible(): boolean {
    const view = this.entry.view;
    return view.phase === 'ready' && view.session !== null && view.decision?.state === 'active';
  }
  private matched(): boolean {
    const entry = this.entry.view, administration = this.current!.view;
    // Even an empty rejection can contain an action correlation from its last verified account context.
    if (administration.session === null) return entry.session !== null && sameContext(entry.session.context, this.currentContext!);
    if (entry.session === null || administration.access?.state !== 'active' || entry.authorization === null) return false;
    if (!sameContext(entry.session.context, administration.session.context)
        || entry.session.access !== administration.session.access
        || entry.authorization.state !== administration.access.state
        || entry.authorization.setupAllowed !== administration.access.setupAllowed
        || entry.authorization.enrollmentAllowed !== administration.access.enrollmentAllowed
        || !sameGrants(entry.authorization.permissions, administration.access.permissions)) return false;
    const scope = administration.capabilities?.householdId ?? administration.household?.householdId ?? null;
    return entry.household === null || scope === null || entry.household.householdId === scope;
  }
  /** No tick obtains new proof, extends a lease, sends a command or queries an original operation. */
  tick(): void {
    if (this.closed) return;
    this.entry.tick(); this.current?.tick();
    const entry = this.entry.view, administration = this.current?.view;
    if (entry.decision?.state === 'authentication_required'
        || (administration?.session === null && administration.notice === 'authentication_required')) {
      this.generation++; this.notice = null; this.entry.expire(); this.retire(); return;
    }
    if (entry.phase === 'ready' && entry.decision?.state !== 'active') {this.notice = null; this.retire(); return;}
    if (this.visible && !this.matched()) {this.visible = false; this.notice = 'context_changed';}
  }
  private async synchronize(generation: number, loaded: boolean): Promise<void> {
    if (!this.live(generation)) return;
    if (!this.eligible()) {this.retire(); return;}
    if (this.current === null) {
      this.current = this.administrationFactory(); this.currentContext = this.entry.view.session!.context; loaded = false;
    }
    const current = this.current;
    if (!loaded) await current.refresh();
    if (!this.live(generation)) return;
    this.currentContext = current.view.session?.context ?? this.currentContext;
    this.tick(); if (!this.live(generation)) return;
    if (!this.eligible()) {this.retire(); return;}
    if (this.matched()) {this.visible = true; return;}
    // Independent proof reads can straddle one transition. One bounded read aligns entry; persistent drift stays hidden.
    await this.entry.refresh();
    if (!this.live(generation)) return;
    this.tick(); if (!this.live(generation)) return;
    if (!this.eligible()) {this.retire(); return;}
    if (this.matched()) this.visible = true;
    else {this.retire(); this.notice = 'context_changed';}
  }
  private async perform(work: (generation: number) => Promise<void>): Promise<void> {
    if (this.closed || this.view.busy) return;
    this.running = true; this.visible = false; this.notice = null;
    const generation = ++this.generation;
    try {await work(generation);} finally {this.running = false;}
  }
  refresh(): Promise<void> {
    return this.perform(async generation => {
      const current = this.current;
      // Both existing controllers retire their prior read generations before fresh proof is requested.
      await Promise.all([this.entry.refresh(), current?.refresh()]);
      await this.synchronize(generation, current !== null);
    });
  }
  private entryWork(work: (controller: EntryController) => Promise<void>): Promise<void> {
    return this.perform(async generation => {await work(this.entry); await this.synchronize(generation, false);});
  }
  submitSetup(name: unknown, timeZone: unknown): Promise<void> {
    return this.entryWork(controller => controller.submitSetup(name, timeZone));
  }
  requestMembership(): Promise<void> {return this.entryWork(controller => controller.requestMembership());}
  recover(key: string): Promise<void> {return this.entryWork(controller => controller.recover(key));}
  dismiss(key: string): Promise<void> {return this.entryWork(controller => controller.dismiss(key));}
  private administrationWork(work: (controller: AdministrationController) => Promise<void>): Promise<void> {
    const current = this.current;
    if (!this.visible || current === null) return Promise.resolve();
    return this.perform(async generation => {
      await work(current);
      if (!this.live(generation)) return;
      this.tick(); if (!this.live(generation)) return;
      if (!this.eligible()) {this.retire(); return;}
      // An action can reject before proof is read. Reconcile both owners, preserving same-authority action notices.
      await Promise.all([this.entry.refresh(), current.reconcile()]);
      await this.synchronize(generation, true);
    });
  }
  submitAdministration(value: unknown): Promise<void> {return this.administrationWork(controller => controller.submit(value));}
  recoverAdministration(key: string): Promise<void> {return this.administrationWork(controller => controller.recover(key));}
  dismissAdministration(key: string): Promise<void> {return this.administrationWork(controller => controller.dismiss(key));}
  async logout(): Promise<void> {
    if (this.closed || this.view.busy) return;
    this.closed = true; this.generation++; this.notice = null; this.retire();
    await this.entry.logout();
  }
  close(): void {
    // Logout disables commands before remote revocation settles. Disposal must still fence that pending result.
    this.closed = true; this.generation++; this.notice = null; this.retire(); this.entry.close();
  }
}
