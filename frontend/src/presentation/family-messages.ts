const en = {
  title: 'Family', balance: 'Your points', posted: 'Posted balance', available: 'Available balance',
  participation: 'Your participation', week: 'Week', month: 'Month', period: 'Period', workDate: 'Work date',
  apply: 'Show participation', earned: 'Earned points in this period', completed: 'Recorded completions',
  verification: 'Estimated points awaiting verification', posting: 'Estimated points awaiting posting',
  effort: 'Elapsed time from recorded starts', unknownEffort: 'No starts were recorded for these completions.',
  minutes: 'minutes', tracked: 'completions with a recorded start',
  history: 'Points history', empty: 'There are no points movements yet.', award: 'Award', reversal: 'Reversal',
  reversedEntry: 'Original award', approved: 'Approved', postingDate: 'Posted',
  loading: 'Loading Family', unavailable: 'Family data is unavailable', refresh: 'Refresh', more: 'More movements',
  stale: 'The last loaded values are shown. Refresh to check for updates.',
  unavailableHelp: 'Refresh to check your current access and points.',
} as const;
const es: Record<keyof typeof en, string> = {
  title: 'Familia', balance: 'Tus puntos', posted: 'Saldo registrado', available: 'Saldo disponible',
  participation: 'Tu participación', week: 'Semana', month: 'Mes', period: 'Período', workDate: 'Fecha del trabajo',
  apply: 'Mostrar participación', earned: 'Puntos ganados en este período', completed: 'Tareas realizadas registradas',
  verification: 'Puntos estimados pendientes de verificación', posting: 'Puntos estimados pendientes de registro',
  effort: 'Tiempo transcurrido desde los inicios registrados', unknownEffort: 'Estas tareas no tienen un inicio registrado.',
  minutes: 'minutos', tracked: 'tareas con un inicio registrado',
  history: 'Historial de puntos', empty: 'Todavía no hay movimientos de puntos.', award: 'Premio', reversal: 'Reversión',
  reversedEntry: 'Premio original', approved: 'Aprobado', postingDate: 'Registrado',
  loading: 'Cargando Familia', unavailable: 'Los datos de Familia no están disponibles', refresh: 'Actualizar',
  more: 'Más movimientos', stale: 'Se muestran los últimos valores cargados. Actualiza para comprobar si hay cambios.',
  unavailableHelp: 'Actualiza para comprobar tu acceso y tus puntos.',
};
export type FamilyMessage = keyof typeof en;
export function familyMessage(key: FamilyMessage, language: 'en' | 'es'): string {
  return (language === 'es' ? es : en)[key];
}
