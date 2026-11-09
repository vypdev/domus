import type {Language} from './messages';

const en = {
  title: 'Calendar', view: 'Calendar view', date: 'Reference date', kind: 'Entry kind',
  timing: 'Task timing', status: 'Task status', priority: 'Priority', category: 'Category',
  mine: 'Only my entries', any: 'All', apply: 'Show calendar', more: 'More entries',
  month: 'Month', week: 'Week', day: 'Day', agenda: 'Agenda', loading: 'Loading calendar.',
  unavailable: 'The calendar could not be loaded. Review the range and try again.',
  pending: 'Recurrence processing is pending. More entries may appear.',
  empty: 'There are no matching entries in this range.', total: 'Matching entries', occurrences: 'Matching tasks',
  planned: 'Planned', due: 'Due', performed: 'Performed', approval: 'Approval',
  manual: 'Manual', fixed_calendar: 'Fixed calendar', completion_relative: 'After completion',
  approved: 'Approved', rejected: 'Rejected', none: 'No approval required', verificationPending: 'Pending approval',
  categoryUnavailable: 'Unavailable category',
  adjusted: 'Original local time',
  relativeReviewRequired: 'Review recurrence. The source task changed.',
  weekStart: 'My week starts on', monday: 'Monday', sunday: 'Sunday',
  recoverPreference: 'Check original week-start change', refreshPreference: 'Reload calendar preference',
  preferenceUnavailable: 'Your calendar preference is unavailable.',
  preferenceUncertain: 'The change is unconfirmed. Check the original request.',
  preferenceRejected: 'The original change could not be confirmed. Review your current preference.',
};
const es: Record<keyof typeof en, string> = {
  title: 'Calendario', view: 'Vista del calendario', date: 'Fecha de referencia', kind: 'Tipo de entrada',
  timing: 'Programación', status: 'Estado de la tarea', priority: 'Prioridad', category: 'Categoría',
  mine: 'Solo mis entradas', any: 'Todas', apply: 'Mostrar calendario', more: 'Más entradas',
  month: 'Mes', week: 'Semana', day: 'Día', agenda: 'Agenda', loading: 'Cargando calendario.',
  unavailable: 'No se pudo cargar el calendario. Revisa el intervalo e inténtalo de nuevo.',
  pending: 'Hay recurrencias pendientes de procesar. Pueden aparecer más entradas.',
  empty: 'No hay entradas que coincidan en este intervalo.', total: 'Entradas que coinciden', occurrences: 'Tareas que coinciden',
  planned: 'Previsto', due: 'Vencimiento', performed: 'Realizado', approval: 'Aprobación',
  manual: 'Manual', fixed_calendar: 'Calendario fijo', completion_relative: 'Tras completar',
  approved: 'Aprobada', rejected: 'Rechazada', none: 'No requiere aprobación', verificationPending: 'Pendiente de aprobación',
  categoryUnavailable: 'Categoría no disponible',
  adjusted: 'Hora local original',
  relativeReviewRequired: 'Revisa la recurrencia. La tarea de origen cambió.',
  weekStart: 'Mi semana empieza el', monday: 'Lunes', sunday: 'Domingo',
  recoverPreference: 'Consultar el cambio original de inicio de semana', refreshPreference: 'Recargar la preferencia del calendario',
  preferenceUnavailable: 'Tu preferencia del calendario no está disponible.',
  preferenceUncertain: 'El cambio está sin confirmar. Consulta la solicitud original.',
  preferenceRejected: 'No se pudo confirmar el cambio original. Revisa tu preferencia actual.',
};
export type CalendarMessage = keyof typeof en;
export function calendarMessage(key: CalendarMessage, locale: Language): string {
  return (locale === 'es' ? es : en)[key];
}
