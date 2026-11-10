/** Preserve one exact request for its verified scope and retire incompatible browser data. */
import {check} from './json-values';
import type {OwnedStorage} from './session-journal';

export class ScopedCommandJournal<Request extends Readonly<{scope: string}>> {
  constructor(private readonly storage: OwnedStorage, private readonly key: string,
    private readonly decode: (raw: string) => Request) {}

  open(scope: string): Request | null {
    const raw = this.storage.getItem(this.key);
    if (raw === null) return null;
    const request = this.decode(raw);
    if (request.scope === scope) return request;
    this.clear(request); return null;
  }

  save(request: Request): void {
    const raw = JSON.stringify(request);
    this.decode(raw); check(this.storage.getItem(this.key) === null);
    this.storage.setItem(this.key, raw);
    check(this.storage.getItem(this.key) === raw);
  }

  clear(request: Request): void {
    check(this.storage.getItem(this.key) === JSON.stringify(request));
    this.storage.removeItem(this.key);
    check(this.storage.getItem(this.key) === null);
  }
}
