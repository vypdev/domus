import type {BaseUnit} from '../domain/inventory';
import type {OverviewView} from './overview-read';

export interface StockAttentionItem {
  readonly id: string;
  readonly name: string;
  readonly unit: BaseUnit;
  readonly available: string;
  readonly minimum: string;
}

export interface StockAttention {
  readonly total: number;
  readonly items: readonly StockAttentionItem[];
}

export type StockAttentionView = OverviewView<StockAttention>;
