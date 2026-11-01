import {EntryController} from '../application/entry-controller';
import type {EntryView} from '../application/entry-controller';
import {EntryReadError} from '../application/ports';
import {BrowserEntropy, BrowserNavigation, ServerClock} from '../adapters/browser-capabilities';
import {HttpEntryServer} from '../adapters/http';
import type {FetchTransport} from '../adapters/http';
import {endpoint} from '../adapters/http-values';
import type {EntryEndpoint} from '../adapters/http-values';
import {SessionJournal} from '../adapters/session-journal';
import type {OwnedStorage} from '../adapters/session-journal';

/** Capabilities of this document only. No parent window, private HA object or host storage access. */
export interface EntryBrowser {
  transport: FetchTransport;
  storage(): OwnedStorage;
  elapsed(): number;
  random(bytes: Uint8Array<ArrayBuffer>): Uint8Array<ArrayBuffer>;
  navigate(path: string): void;
  events: EventTarget;
  visibility: EventTarget;
  schedule(tick: () => void, delay: number): () => void;
}
type OwnedController = Readonly<{controller: EntryController; clock: ServerClock}>;

/** Composition/lifecycle only; commands, authorization and recovery stay in the Application layer. */
export class EntryRuntime {
  private readonly target: EntryEndpoint;
  private readonly navigation: BrowserNavigation;
  private current: OwnedController;
  private started = false;
  private active = false;
  private paused = false;
  private disposed = false;
  private timerEpoch = 0;
  private cancelTimer: (() => void) | null = null;
  constructor(target: EntryEndpoint, private readonly browser: EntryBrowser,
    private readonly changed: (view: EntryView) => void, private readonly failed: () => void = () => {}) {
    this.target = endpoint(target); this.navigation = new BrowserNavigation(this.target, path => browser.navigate(path));
    this.current = this.compose();
  }
  private compose(): OwnedController {
    const clock = new ServerClock(() => this.browser.elapsed());
    const journal = new SessionJournal({getItem: key => this.browser.storage().getItem(key),
      setItem: (key, value) => this.browser.storage().setItem(key, value),
      removeItem: key => this.browser.storage().removeItem(key)});
    const server = new HttpEntryServer(this.target, this.browser.transport);
    return {clock, controller: new EntryController(this.target.deployment, server, journal, clock,
      new BrowserEntropy(bytes => this.browser.random(bytes)))};
  }
  get view(): EntryView {return this.current.controller.view;}
  private publish(): void {
    try {this.changed(this.view);} catch {/* A renderer failure cannot change authority or interrupt resource cleanup. */}
  }
  private stopTimer(): void {
    this.timerEpoch++; const cancel = this.cancelTimer; this.cancelTimer = null;
    if (cancel !== null) {try {cancel();} catch {/* The epoch still fences a canceled callback delivered late. */}}
  }
  private arm(): void {
    this.stopTimer();
    const owned = this.current, view = this.view;
    if (!this.active || view.session === null) return;
    let now: number;
    try {now = owned.clock.now();}
    catch {owned.controller.tick(); this.publish(); return;}
    const deadlines = [view.session.expiresAt, ...view.journal?.records.map(record => record.expiresAt) ?? []];
    const delay = Math.max(1, Math.min(1000, ...deadlines.map(deadline => deadline - now)));
    const epoch = this.timerEpoch;
    try {
      this.cancelTimer = this.browser.schedule(() => {
        if (epoch !== this.timerEpoch || !this.active || this.current !== owned) return;
        this.cancelTimer = null; owned.controller.tick(); this.publish(); this.later();
      }, delay);
    } catch {
      this.dispose();
      try {this.failed();} catch {/* The runtime is already closed even if its outer failure view fails. */}
      throw new EntryReadError('unavailable');
    }
  }
  private later(): void {try {this.arm();} catch {/* Disposal and bounded failure notification already completed. */}}
  private async perform(work: (controller: EntryController) => Promise<void>): Promise<void> {
    if (this.disposed || !this.active) return;
    const owned = this.current, pending = work(owned.controller);
    this.publish(); this.arm();
    try {await pending;}
    finally {if (this.active && this.current === owned) {this.publish(); this.arm();}}
  }
  async start(): Promise<void> {
    if (this.started || this.disposed) return;
    this.started = true; this.active = true;
    this.browser.events.addEventListener('pagehide', this.hide);
    this.browser.events.addEventListener('pageshow', this.show);
    this.browser.visibility.addEventListener('visibilitychange', this.visible);
    await this.refresh();
  }
  private readonly hide = (event: Event): void => {
    if ('persisted' in event && event.persisted === true && this.active) {
      this.active = false; this.paused = true; this.stopTimer(); this.current.controller.close(); this.publish();
    } else this.dispose();
  };
  private readonly show = (event: Event): void => {
    if (!this.paused || !('persisted' in event) || event.persisted !== true || this.disposed) return;
    this.paused = false; this.current = this.compose(); this.active = true;
    void this.refresh().catch(() => {this.dispose();});
  };
  private readonly visible = (): void => {
    if (!this.active) return;
    this.current.controller.tick(); this.publish(); this.later();
  };
  refresh(): Promise<void> {return this.perform(controller => controller.refresh());}
  submitSetup(name: unknown, timeZone: unknown): Promise<void> {
    return this.perform(controller => controller.submitSetup(name, timeZone));
  }
  requestMembership(): Promise<void> {return this.perform(controller => controller.requestMembership());}
  recover(key: string): Promise<void> {return this.perform(controller => controller.recover(key));}
  dismiss(key: string): Promise<void> {return this.perform(controller => controller.dismiss(key));}
  signIn(): void {if (!this.disposed && !this.paused) this.navigation.signIn();}
  reopen(): void {if (!this.disposed && !this.paused) this.navigation.reopen();}
  async logout(): Promise<void> {
    if (this.disposed || !this.active) return;
    const owned = this.current; this.active = false; this.stopTimer();
    const pending = owned.controller.logout(); this.publish();
    try {await pending;} finally {if (!this.disposed && this.current === owned) this.publish();}
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true; this.active = false; this.paused = false; this.stopTimer();
    this.browser.events.removeEventListener('pagehide', this.hide);
    this.browser.events.removeEventListener('pageshow', this.show);
    this.browser.visibility.removeEventListener('visibilitychange', this.visible);
    this.current.controller.close(); this.publish();
  }
}
