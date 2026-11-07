import type {Language} from './messages';

const en = {
  title: 'Calendar', view: 'Calendar view', date: 'Reference date', kind: 'Entry kind',
  timing: 'Task timing', status: 'Task status', priority: 'Priority', category: 'Category tag',
  mine: 'Only my entries', any: 'All', apply: 'Show calendar', more: 'More entries',
  month: 'Month', week: 'Week', day: 'Day', agenda: 'Agenda', loading: 'Loading calendar.',
  unavailable: 'The calendar could not be loaded. Review the range and try again.',
  pending: 'Recurrence processing is pending. More entries may appear.',
  empty: 'There are no matching entries in this range.', total: 'Matching entries',
  planned: 'Planned', due: 'Due', performed: 'Performed', approval: 'Approval',
  manual: 'Manual', fixed_calendar: 'Fixed calendar', completion_relative: 'After completion',
  approved: 'Approved', rejected: 'Rejected', none: 'No approval required', verificationPending: 'Pending approval',
  adjusted: 'Original local time',
};
const es: Record<keyof typeof en, string> = {
  title: 'Calendario', view: 'Vista del calendario', date: 'Fecha de referencia', kind: 'Tipo de entrada',
  timing: 'Programación', status: 'Estado de la tarea', priority: 'Prioridad', category: 'Etiqueta de categoría',
  mine: 'Solo mis entradas', any: 'Todas', apply: 'Mostrar calendario', more: 'Más entradas',
  month: 'Mes', week: 'Semana', day: 'Día', agenda: 'Agenda', loading: 'Cargando calendario.',
  unavailable: 'No se pudo cargar el calendario. Revisa el intervalo e inténtalo de nuevo.',
  pending: 'Hay recurrencias pendientes de procesar. Pueden aparecer más entradas.',
  empty: 'No hay entradas que coincidan en este intervalo.', total: 'Entradas que coinciden',
  planned: 'Previsto', due: 'Vencimiento', performed: 'Realizado', approval: 'Aprobación',
  manual: 'Manual', fixed_calendar: 'Calendario fijo', completion_relative: 'Tras completar',
  approved: 'Aprobada', rejected: 'Rechazada', none: 'No requiere aprobación', verificationPending: 'Pendiente de aprobación',
  adjusted: 'Hora local original',
};
export type CalendarMessage = keyof typeof en;
export function calendarMessage(key: CalendarMessage, locale: Language): string {
  return (locale === 'es' ? es : en)[key];
}
