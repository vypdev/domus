import type {Language} from './messages';
const en = {
  history:'Earlier material usage', historyHelp:'Reopening does not cancel or return earlier usage. Review each closed completion separately.',
  historyLoad:'Review earlier usage', historyMore:'Next closed completion', historyEmpty:'No earlier completions.', completion:'Performed', closed:'Reopened',
  plan: 'Materials (optional)', planHelp: 'Plan Pantry products for this task. Planning does not consume stock. You can create a task with only a title.',
  open: 'Add materials', product: 'Pantry product', choose: 'Choose a product', add: 'Add to plan', more: 'More products', refresh: 'Refresh material choices',
  planned: 'Planned quantity', actual: 'Actual quantity', confirmed: 'Confirmed consumption', pendingTotal: 'Total awaiting confirmation',
  remove: 'Remove material', clear: 'Remove material plan', empty: 'No products on this page. Add products in Inventory, or create the task without materials.',
  unavailable: 'Material choices could not be loaded. Your plan is retained. Retry when the service is available.',
  forbidden: 'Your current access does not allow linking materials. Private choices are hidden. Remove the retained plan or review it after access is restored.',
  forbiddenEmpty: 'Your current access does not allow adding materials. No material plan has been added. Review your access, then refresh Tasks to try again.',
  invalid_input: 'Review the material selection. Choose up to 32 different products.',
  unreviewed: 'Material needs current review', quantityHelp: 'Use the displayed unit. Zero means none planned.',
  invalidQuantity: 'Enter a nonnegative quantity in the displayed unit and precision.',
  limit: 'Up to 32 different products can be planned.', whole: 'Whole quantities', decimal: 'Up to 6 decimal places',
  piece: 'pieces', pieceSingle: 'piece', gram: 'g', millilitre: 'mL', unit: 'Unit code', source: 'Source', pantry: 'Pantry', unknown: 'Unavailable',
  notRecorded: 'Not recorded', notConfirmed: 'Not confirmed', noMovement: 'No stock movement',
  outcomes: 'Material consumption', independent: 'Task completion, approval and points are separate from each material result. Restocking or restoring access does not settle pending usage automatically.',
  pending_recording: 'Actual quantity not recorded', pending_authorization: 'Authorization required', pending_regularization: 'Inventory review required',
  pending_processing: 'Settlement pending', not_used: 'Not used · no stock movement', posted: 'Consumption confirmed', corrected: 'Corrected total confirmed', dismissed: 'Usage dismissed',
  actual_quantity_required: 'Record the quantity actually used, including zero.', material_permission_required: 'An authorized member must explicitly settle this usage.',
  explicit_settlement_required: 'Review this usage and explicitly settle it.', awaiting_inventory_confirmation: 'Check Inventory and explicitly retry settlement.',
  inventory_unavailable: 'Inventory is unavailable. Retry when it is available.', insufficient_stock: 'Not enough stock. Review or replenish Inventory, then explicitly retry here.',
  inventory_binding_changed: 'The captured Inventory reference changed. Ask a manager to review it.',
  settle: 'Settle pending usage', record: 'Record actual usage', reason: 'Reason for recording', reasonHelp: 'Explain the recorded actual quantity. Up to 1,000 characters.',
  denied: 'Your current access does not allow settling this usage. The task and any draft are retained.',
  changed: 'This usage changed. Your draft is retained. Review the current result before saving.', review: 'Review current usage',
  saved: 'Material request recorded. The result below shows whether Inventory confirmed it.',
};
const es: typeof en = {
  history:'Consumos anteriores', historyHelp:'Reabrir no cancela ni devuelve el consumo anterior. Revisa cada realización cerrada por separado.',
  historyLoad:'Revisar consumos anteriores', historyMore:'Siguiente realización cerrada', historyEmpty:'No hay realizaciones anteriores.', completion:'Realizada', closed:'Reabierta',
  plan: 'Materiales (opcional)', planHelp: 'Planifica productos de Despensa para esta tarea. Planificar no consume existencias. Puedes crear la tarea solo con un título.',
  open: 'Añadir materiales', product: 'Producto de Despensa', choose: 'Elige un producto', add: 'Añadir al plan', more: 'Más productos', refresh: 'Actualizar materiales disponibles',
  planned: 'Cantidad prevista', actual: 'Cantidad utilizada', confirmed: 'Consumo contabilizado', pendingTotal: 'Total pendiente de confirmar',
  remove: 'Quitar material', clear: 'Quitar plan de materiales', empty: 'No hay productos en esta página. Añádelos en Inventario o crea la tarea sin materiales.',
  unavailable: 'No se han podido cargar los materiales. Tu plan se conserva. Reintenta cuando el servicio esté disponible.',
  forbidden: 'Tu acceso actual no permite vincular materiales. Las opciones privadas están ocultas. Quita el plan conservado o revísalo cuando recuperes el acceso.',
  forbiddenEmpty: 'Tu acceso actual no permite añadir materiales. No se ha añadido ningún plan de materiales. Revisa tu acceso y después actualiza Tareas para volver a intentarlo.',
  invalid_input: 'Revisa la selección de materiales. Puedes elegir hasta 32 productos distintos.',
  unreviewed: 'Material pendiente de revisión actual', quantityHelp: 'Usa la unidad indicada. Cero significa que no prevés utilizarlo.',
  invalidQuantity: 'Introduce una cantidad no negativa con la unidad y precisión indicadas.',
  limit: 'Puedes planificar hasta 32 productos distintos.', whole: 'Cantidades enteras', decimal: 'Hasta 6 decimales',
  piece: 'unidades', pieceSingle: 'unidad', gram: 'g', millilitre: 'mL', unit: 'Código de unidad', source: 'Origen', pantry: 'Despensa', unknown: 'No disponible',
  notRecorded: 'Sin registrar', notConfirmed: 'Sin confirmar', noMovement: 'Sin movimiento de existencias',
  outcomes: 'Consumo de materiales', independent: 'La realización, aprobación y puntos de la tarea son independientes del resultado de cada material. Reponer existencias o recuperar permisos no contabiliza automáticamente los consumos pendientes.',
  pending_recording: 'Cantidad utilizada sin registrar', pending_authorization: 'Falta autorización', pending_regularization: 'Requiere revisión de Inventario',
  pending_processing: 'Contabilización pendiente', not_used: 'Sin utilizar · sin movimiento de existencias', posted: 'Consumo contabilizado', corrected: 'Total corregido contabilizado', dismissed: 'Consumo descartado',
  actual_quantity_required: 'Registra la cantidad utilizada, incluido cero.', material_permission_required: 'Una persona autorizada debe contabilizar explícitamente este consumo.',
  explicit_settlement_required: 'Revisa y contabiliza explícitamente este consumo.', awaiting_inventory_confirmation: 'Comprueba Inventario y reintenta explícitamente la contabilización.',
  inventory_unavailable: 'Inventario no está disponible. Reintenta cuando lo esté.', insufficient_stock: 'No hay existencias suficientes. Revisa o repón Inventario y después reintenta aquí.',
  inventory_binding_changed: 'La referencia de Inventario cambió. Pide a un responsable que la revise.',
  settle: 'Contabilizar consumo pendiente', record: 'Registrar consumo real', reason: 'Motivo del registro', reasonHelp: 'Explica la cantidad utilizada. Hasta 1.000 caracteres.',
  denied: 'Tu acceso actual no permite contabilizar este consumo. La tarea y el borrador se conservan.',
  changed: 'Este consumo ha cambiado. Tu borrador se conserva. Revisa el resultado actual antes de guardar.', review: 'Revisar consumo actual',
  saved: 'Solicitud de materiales registrada. El resultado inferior indica si Inventario la ha confirmado.',
};
export type TaskMaterialMessage = keyof typeof en;
export function materialMessage(key: TaskMaterialMessage, language: Language): string {return (language === 'es' ? es : en)[key];}
export function materialUnit(unit: string | undefined, language: Language, quantity?: string): string {
  if (unit === 'piece' && quantity === '1') return materialMessage('pieceSingle', language);
  return unit === 'piece' || unit === 'gram' || unit === 'millilitre' ? materialMessage(unit, language)
    : materialMessage('unit', language) + ': ' + (unit ?? materialMessage('unknown', language));
}
export function materialSource(source: string | undefined, language: Language): string {
  return materialMessage('source', language) + ': ' + (source === 'pantry' ? materialMessage('pantry', language) : source ?? materialMessage('unknown', language));
}
