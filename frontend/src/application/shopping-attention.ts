import type {ShoppingItem} from '../domain/inventory';
import type {OverviewView} from './overview-read';

export type ShoppingAttentionItem = Pick<ShoppingItem, 'productId' | 'extraId' | 'name' | 'unit' | 'total'>;

export interface ShoppingAttention {
  readonly total: number;
  readonly items: readonly ShoppingAttentionItem[];
}

export type ShoppingAttentionView = OverviewView<ShoppingAttention>;
