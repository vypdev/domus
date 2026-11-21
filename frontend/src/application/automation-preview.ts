import type {InventoryScope, InventoryServer} from './inventory-controller';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';
import type {JournalContext} from '../domain/journal';
import {taskText} from '../domain/tasks';

export interface AutomationPreviewScope extends InventoryScope {
  readonly householdId: string;
  readonly authorization?: string;
}
export interface AutomationPreviewDraft {
  readonly title: string;
  readonly productId: string | null;
}
export interface AutomationPreviewServer {
  access(context: JournalContext, householdId: string): EntryRead<void>;
  preview(context: JournalContext, draft: AutomationPreviewDraft): EntryRead<boolean>;
}
interface ProductOption {
  readonly id: string;
  readonly name: string;
}
interface ProductPage {
  readonly products: readonly ProductOption[];
  readonly after: string | null;
  readonly next: string | null;
}
type Issue = 'title' | 'preview';
interface ReadyPreview {
  readonly state: 'ready';
  readonly title: string;
  readonly selected: ProductOption | null;
  readonly catalog: ProductPage;
  readonly catalogUnavailable: boolean;
  readonly busy: 'products' | 'preview' | null;
  readonly result: boolean | null;
  readonly issue: Issue | null;
}
export type AutomationPreviewView = ReadyPreview | Readonly<{state: 'loading' | 'denied' | 'unavailable'}>;

export type AutomationPreviewIntent = Readonly<{type: 'retry' | 'first' | 'next' | 'preview'}>
  | Readonly<{type: 'title'; value: string}> | Readonly<{type: 'product'; value: string | null}>;

/** Keep a draft in the verified household only, and recheck access on every return. */
export class AutomationPreviewController {
  private scope: AutomationPreviewScope | null = null;
  private visible = false;
  private ready: ReadyPreview | null = null;
  private pending: EntryRead<unknown> | null = null;
  private granted = false;
  private replacement: AutomationPreviewDraft | null = null;

  constructor(private readonly server: AutomationPreviewServer, private readonly inventory: Pick<InventoryServer, 'read'>,
    private readonly publish: (view: AutomationPreviewView | null) => void) {}

  bind(scope: AutomationPreviewScope | null, visible = false): void {
    visible = scope !== null && visible;
    const same = scope?.key === this.scope?.key;
    if (same && this.scope?.authorization === scope?.authorization && this.visible === visible) return;
    this.pending?.cancel();
    this.pending = null;
    if (!same) {this.ready = null; this.replacement = null;}
    this.scope = scope;
    this.visible = visible;
    this.granted = false;
    if (visible) void this.refresh();
    else this.publish(null);
  }

  draft(): AutomationPreviewDraft | null {
    const ready = this.ready;
    return this.visible && this.granted && ready?.busy === null
      ? {title: ready.title, productId: ready.selected?.id ?? null} : null;
  }

  replaceDraft(draft: AutomationPreviewDraft): void {
    this.replacement = draft;
    if (this.ready !== null && this.pending === null) this.update(this.ready);
  }

  async handle(intent: AutomationPreviewIntent | undefined): Promise<void> {
    if (intent?.type === 'retry') {
      await this.refresh();
      return;
    }
    const current = this.ready;
    if (!this.granted || current === null || current.busy !== null) return;
    if (intent?.type === 'title' && typeof intent.value === 'string') {
      this.update({...current, title: intent.value, result: null, issue: null});
    } else if (intent?.type === 'product') {
      const selected = current.catalog.products.find(product => product.id === intent.value);
      if (intent.value === null || selected !== undefined) {
        this.update({...current, selected: selected ?? null, result: null, issue: null});
      }
    } else if (intent?.type === 'preview') {
      await this.preview(current);
    } else if (intent?.type === 'first' && current.catalog.after !== null) {
      await this.products(null);
    } else if (intent?.type === 'next' && current.catalog.next !== null) {
      await this.products(current.catalog.next);
    }
  }

  private update(view: ReadyPreview): void {
    const draft = this.replacement;
    if (draft !== null && view.busy === null) {
      const selected = draft.productId === null ? null
        : view.catalog.products.find(product => product.id === draft.productId)
          ?? {id: draft.productId, name: draft.productId};
      view = {...view, title: draft.title, selected, result: null, issue: null};
      this.replacement = null;
    }
    this.ready = view;
    this.publish(view);
  }

  private async settle<T>(request: EntryRead<T>, success: (value: T) => void, failure: () => void): Promise<void> {
    this.pending = request;
    let value: T;
    try {
      value = await request.result;
    } catch (error) {
      if (this.pending !== request) return;
      this.pending = null;
      if (error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required')) {
        this.granted = false;
        this.ready = null;
        this.replacement = null;
        this.publish({state: 'denied'});
      } else failure();
      return;
    }
    if (this.pending !== request) return;
    this.pending = null;
    success(value);
  }

  private async refresh(): Promise<void> {
    const scope = this.scope;
    if (scope === null || !this.visible || this.pending !== null) return;
    this.granted = false;
    this.publish({state: 'loading'});
    await this.settle(this.server.access(scope.context, scope.householdId), () => {
      this.granted = true;
      if (this.ready !== null) this.ready = {...this.ready, busy: null, result: null};
      void this.products(null);
    }, () => this.publish({state: 'unavailable'}));
  }

  private async products(after: string | null): Promise<void> {
    const current: ReadyPreview = this.ready ?? {
      state: 'ready', title: '', selected: null, catalog: {products: [], after: null, next: null},
      catalogUnavailable: false, busy: null, result: null, issue: null,
    };
    this.update({...current, catalogUnavailable: false, busy: 'products', issue: null});
    await this.settle(this.inventory.read(this.scope!, after), report => {
      const products = report.products.map(({id, name}) => ({id, name}));
      const selected = products.find(product => product.id === current.selected?.id) ?? current.selected;
      this.update({...current, selected, catalog: {products, after, next: report.cursor}, catalogUnavailable: false, issue: null});
    }, () => this.update({...current, catalogUnavailable: true, issue: null}));
  }

  private async preview(current: ReadyPreview): Promise<void> {
    let title: string;
    try {title = taskText(current.title, 160, true);}
    catch {
      this.update({...current, result: null, issue: 'title'});
      return;
    }
    this.update({...current, busy: 'preview', result: null, issue: null});
    await this.settle(this.server.preview(this.scope!.context, {title, productId: current.selected?.id ?? null}),
      result => this.update({...current, result, issue: null}),
      () => this.update({...current, result: null, issue: 'preview'}));
  }
}
