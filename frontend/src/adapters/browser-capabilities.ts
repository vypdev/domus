import {EntryReadError} from '../application/ports';
import type {EntryClock, EntryEntropy} from '../application/ports';
import {endpoint} from './http-values';
import type {EntryEndpoint} from './http-values';

/** Server epoch plus monotonic elapsed time; no browser wall clock can renew an absolute lease. */
export class ServerClock implements EntryClock {
  private epoch: number | null = null;
  private anchoredAt = 0;
  private lastElapsed: number | null = null;
  private failed = false;
  constructor(private readonly elapsed: () => number = () => performance.now()) {}
  private fail(): never {this.failed = true; throw new Error('clock_unavailable');}
  private sample(): number {
    if (this.failed) this.fail();
    let value: number;
    try {value = this.elapsed();} catch {return this.fail();}
    if (!Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER
        || (this.lastElapsed !== null && value < this.lastElapsed)) this.fail();
    this.lastElapsed = value; return value;
  }
  private at(elapsed: number): number | null {
    if (this.epoch === null) return null;
    const now = this.epoch + Math.floor(elapsed - this.anchoredAt);
    if (!Number.isSafeInteger(now)) this.fail();
    return now;
  }
  anchor(serverTime: number): void {
    if (!Number.isSafeInteger(serverTime) || serverTime < 0) this.fail();
    const elapsed = this.sample();
    this.epoch = Math.max(serverTime, this.at(elapsed) ?? 0); this.anchoredAt = elapsed;
  }
  now(): number {
    if (this.epoch === null) throw new Error('clock_unavailable');
    return this.at(this.sample())!;
  }
}

type RandomFill = (bytes: Uint8Array<ArrayBuffer>) => Uint8Array<ArrayBuffer>;
/** Exactly 128 bits from Web Crypto; failure never falls back to a timestamp or Math.random. */
export class BrowserEntropy implements EntryEntropy {
  constructor(private readonly fill: RandomFill = bytes => crypto.getRandomValues(bytes)) {}
  requestKey(): string {
    const bytes = new Uint8Array(16);
    try {
      if (this.fill(bytes) !== bytes) throw new Error();
    } catch {throw new Error('entropy_unavailable');}
    return 'req_' + Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  }
}

/** Deliberate navigation has only two closed destinations inside the accepted same-origin base. */
export class BrowserNavigation {
  private readonly target: EntryEndpoint;
  constructor(target: EntryEndpoint, private readonly navigate: (path: string) => void) {this.target = endpoint(target);}
  private move(path: string): void {
    const navigate = this.navigate;
    try {navigate(path);} catch {throw new EntryReadError('unavailable');}
  }
  signIn(): void {
    if (this.target.deployment !== 'standalone') throw new EntryReadError('forbidden');
    this.move(this.target.applicationBase + 'api/v1/auth/start');
  }
  reopen(): void {this.move(this.target.applicationBase);}
}
