import {html, nothing} from 'lit';
import type {TemplateResult} from 'lit';
import {registerFeedback} from '@vypdev/ha-ui/feedback';
import {feedbackState} from '@vypdev/ha-ui/feedback-contracts';
import type {InventoryState} from '../application/inventory-controller';
import {inventoryMessage, inventoryUnitMessage} from './inventory-messages';
import type {InventoryMessage} from './inventory-messages';
import type {Language} from './messages';

const MOVEMENT_SAVED = {
  'inventory.intake': 'added', 'inventory.adjust': 'adjusted',
  'inventory.correct-intake': 'reversed', 'inventory.transfer': 'moved',
} as const;
const SHOPPING_SAVED = {
  'shopping.purchase': 'purchaseSaved', 'shopping.receive': 'arrivalSaved',
  'shopping.cancel-balance': 'cancelSaved', 'shopping.void-receipt': 'voidSaved',
  'shopping.correct-posted-receipt': 'postedCorrectionSaved', 'shopping.return-receipt': 'returnSaved',
  'shopping.post-receipt': 'stockPosted', 'shopping.add-extra': 'extraAdded',
  'shopping.clear-extra': 'extraCleared', 'shopping.record-session': 'sessionSaved',
} as const;
const LOCATION_SAVED = {
  'inventory.rename-location': 'locationRenamed', 'inventory.archive-location': 'locationArchived',
  'inventory.restore-location': 'locationRestored',
} as const;

/** Both destinations describe the result of the same application-owned operation. */
export function inventoryOperationFeedback(view: InventoryState, language: Language,
  productLink: TemplateResult | typeof nothing = nothing, unavailable: InventoryMessage = 'unavailable') {
  const text = (key: InventoryMessage) => inventoryMessage(key, language);
  const {result, notice} = view;
  const saved = result !== null && result.kind !== 'rejected' ? result : null;
  const movement = saved?.movement;
  const message = result?.kind === 'rejected'
    ? result.reason === 'permission_denied' && result.command.action === 'shopping.add-extra'
      ? 'shoppingRequestDenied' : result.reason === 'permission_denied'
          && (result.command.action === 'shopping.correct-posted-receipt' || result.command.action === 'shopping.return-receipt')
        ? 'shoppingAndStockDenied' : result.reason === 'permission_denied'
            && result.command.action.startsWith('shopping.') && result.command.action !== 'shopping.post-receipt'
          ? 'shoppingManagementDenied' : result.reason === 'inventory_stock_capacity' && result.command.action === 'shopping.post-receipt'
        ? 'shoppingPostingCapacity' : result.reason
    : view.accessDenied ? 'inventoryAccessDenied' : notice;
  return html`${message === null ? nothing : html`<vyp-ha-feedback
      .state=${feedbackState({kind:'notice', tone:'warning', message:text(message === 'unavailable' ? unavailable : message)})}></vyp-ha-feedback>`}
    ${view.accessDenied && view.pending ? html`<p role="status">${text('uncertain')}</p>` : nothing}
    ${saved === null ? nothing : html`<p role="status">${text(saved.kind === 'historical'
      ? 'historical' : movement ? MOVEMENT_SAVED[movement.action] : saved.shoppingAction
        ? SHOPPING_SAVED[saved.shoppingAction] : saved.barcodeSaved
          ? saved.barcodeSaved.linked ? 'barcodeLinkedSaved' : 'barcodeRemovedSaved'
          : saved.replenishmentSaved ? 'replenishmentSaved' : saved.locationSaved ? 'locationSaved'
            : saved.locationChanged ? LOCATION_SAVED[saved.locationChanged.action] : 'registered')}
      ${saved.barcodeSaved ? html`<code>${saved.barcodeSaved.barcode}</code>` : nothing}
      ${movement ? html`${language === 'es' ? movement.quantity.replace('.', ',') : movement.quantity} ${text(inventoryUnitMessage(movement.unit, movement.quantity))}` : nothing}</p>
      ${productLink}
      <details><summary>${text('receipt')}</summary>
        <p>${text('operation')} <code>${saved.operationId}</code></p>
        ${movement ? html`<p>${text('movement')} <code>${movement.movementId}</code></p>` : nothing}
      </details>`}`;
}

registerFeedback();
