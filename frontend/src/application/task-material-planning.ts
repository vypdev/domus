/** Optional bounded catalog discovery. Inventory owns bindings, units and write authority. */
import type {InventoryScope, InventoryServer} from './inventory-controller';
import {EntryReadError} from './ports';
import type {EntryRead} from './ports';
import type {BaseUnit, InventoryReport} from '../domain/inventory';
import {taskMaterialSelections, taskQuantityInput} from '../domain/tasks';
import type {TaskMaterialSelection} from '../domain/tasks';

export interface MaterialChoice {readonly referenceId: string; readonly name: string; readonly unit: BaseUnit;}
export interface MaterialPlanRow {
  readonly referenceId: string; readonly input: string; readonly choice: MaterialChoice | null;
}
export interface MaterialPlanScope extends InventoryScope {readonly canLink: boolean;}
export interface TaskMaterialPlanView {
  readonly open: boolean; readonly busy: boolean; readonly canLink: boolean; readonly readOnly: boolean;
  readonly rows: readonly MaterialPlanRow[]; readonly choices: readonly MaterialChoice[];
  readonly cursor: string | null; readonly notice: 'forbidden' | 'unavailable' | 'invalid_input' | null;
}
const empty = (): TaskMaterialPlanView => Object.freeze({open: false, busy: false, canLink: false, readOnly: true,
  rows: Object.freeze([]), choices: Object.freeze([]), cursor: null, notice: null});
export class TaskMaterialPlanning {
  private scope: MaterialPlanScope | null = null;
  private state = empty();
  private read: EntryRead<InventoryReport> | null = null;
  constructor(private readonly server: Pick<InventoryServer, 'read'>) {}
  get view(): TaskMaterialPlanView {return this.state;}
  get draftKey(): string {return JSON.stringify(this.state.rows.map(row => [row.referenceId, row.input]));}
  private set(patch: Partial<TaskMaterialPlanView>): void {this.state = Object.freeze({...this.state, ...patch});}
  private cancel(): void {
    const read = this.read; this.read = null; this.set({busy: false});
    try {read?.cancel();} catch {/* Retirement fences late results even if transport cancellation fails. */}
  }
  private retire(): void {
    this.set({choices: Object.freeze([]), cursor: null,
      rows: Object.freeze(this.state.rows.map(row => Object.freeze({...row, choice: null})))});
  }
  bind(scope: MaterialPlanScope | null): void {
    const changed = scope?.key !== this.scope?.key;
    if (changed || scope === null || scope.canLink !== this.scope?.canLink || scope.readOnly !== this.scope?.readOnly) this.cancel();
    if (changed || scope === null) this.state = empty();
    this.scope = scope;
    if (scope === null) return;
    if (!scope.canLink) {this.retire(); if (this.state.rows.length) this.set({notice:'forbidden'});}
    this.set({canLink: scope.canLink, readOnly: scope.readOnly});
  }
  async load(more = false): Promise<void> {
    const scope = this.scope;
    if (scope === null || !scope.canLink || this.state.busy || more && this.state.cursor === null) return;
    const cursor = more ? this.state.cursor : null;
    if (!more) this.retire();
    this.set({open: true, busy: true, notice: null});
    const request = this.server.read(scope, cursor); this.read = request;
    try {
      const report = await request.result;
      if (this.read !== request || this.scope?.key !== scope.key) return;
      if (!report.mayManage) {this.retire(); this.set({canLink: false, notice: 'forbidden'}); return;}
      const choices = Object.freeze(report.products.map(({referenceId, name, unit}) => Object.freeze({referenceId, name, unit})));
      this.set({choices, cursor: report.cursor, rows: Object.freeze(this.state.rows.map(row =>
        Object.freeze({...row, choice: choices.find(choice => choice.referenceId === row.referenceId) ?? row.choice})))});
    } catch (error) {
      if (this.read !== request) return;
      const denied = error instanceof EntryReadError && (error.code === 'forbidden' || error.code === 'authentication_required');
      if (denied) this.retire();
      this.set({notice: denied ? 'forbidden' : 'unavailable', ...denied ? {canLink: false} : {}});
    } finally {if (this.read === request) {this.read = null; this.set({busy: false});}}
  }
  add(referenceId: string): void {
    const choice = this.state.choices.find(value => value.referenceId === referenceId);
    if (!this.state.canLink || this.state.readOnly || !choice || this.state.rows.length >= 32
        || this.state.rows.some(row => row.referenceId === referenceId)) {this.set({notice: 'invalid_input'}); return;}
    this.set({rows: Object.freeze([...this.state.rows, Object.freeze({referenceId, input: '1', choice})]), notice: null});
  }
  edit(referenceId: string, input: string): void {
    this.set({rows: Object.freeze(this.state.rows.map(row => row.referenceId === referenceId ? Object.freeze({...row, input}) : row)), notice: null});
  }
  remove(referenceId: string): void {
    const rows = Object.freeze(this.state.rows.filter(row => row.referenceId !== referenceId));
    this.set({rows, notice: rows.length && !this.state.canLink ? 'forbidden' : null});
  }
  selections(): readonly TaskMaterialSelection[] | null | undefined {
    if (this.state.rows.length === 0) return undefined;
    if (!this.state.canLink || this.state.rows.some(row => row.choice === null)) return null;
    const result: TaskMaterialSelection[] = [];
    for (const row of this.state.rows) {
      const quantity = taskQuantityInput(row.input, row.choice!.unit === 'piece' ? 0 : 6);
      if (quantity === null) return null;
      result.push({reference_id: row.referenceId, planned_quantity: quantity});
    }
    return taskMaterialSelections(result);
  }
  clear(): void {this.set({rows: Object.freeze([]), open: false, notice: null});}
}
