import {DAILY_RESOLUTIONS} from '../application/automation-schedule-preview';
import type {AutomationScheduleServer, DailyAutomationTime, SchedulePreviewScope} from '../application/automation-schedule-preview';
import {civilDate} from '../domain/civil-date';
import {BoundedHTTP} from './http-transport';
import type {FetchTransport} from './http-transport';
import type {EntryEndpoint} from './http-values';
import {check, choice, fields, integer, text} from './json-values';

function dailyTime(value: unknown, time: string): DailyAutomationTime {
  const row = fields(value, ['requested_date', 'resolved_local', 'instant_ms', 'offset_seconds', 'resolution'], []);
  const requestedDate = row.requested_date, resolvedLocal = text(row.resolved_local, 23);
  const instantMs = integer(row.instant_ms, 0), offset = integer(row.offset_seconds, -86399);
  const resolution = choice(row.resolution, DAILY_RESOLUTIONS);
  check(civilDate(requestedDate) && civilDate(resolvedLocal.slice(0, 10))
    && /^\d{4}-\d{2}-\d{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}$/u.test(resolvedLocal)
    && offset <= 86399 && Date.parse(resolvedLocal + 'Z') - offset * 1000 === instantMs);
  const nominal = requestedDate + 'T' + time + ':00.000';
  check(resolution === 'gap_first_valid' ? resolvedLocal > nominal : resolvedLocal === nominal);
  return {requestedDate, resolvedLocal, instantMs, resolution};
}

export class HttpAutomationSchedulePreview implements AutomationScheduleServer {
  private readonly network: BoundedHTTP;

  constructor(target: EntryEndpoint, transport: FetchTransport) {
    this.network = new BoundedHTTP(target, transport);
  }

  daily(scope: SchedulePreviewScope, time: string) {
    return this.network.owned(async signal => {
      const route = 'automation/schedule-preview?time=' + encodeURIComponent(time);
      const raw = await this.network.get(route, scope.context, signal);
      const result = fields(raw, ['time_zone', 'requested_time', 'items'], []);
      check(result.time_zone === scope.timeZone && result.requested_time === time
        && Array.isArray(result.items) && result.items.length === 5);
      const items = result.items.map(value => dailyTime(value, time));
      let previousInstant = -1, previousDate = '';
      for (const item of items) {
        check(item.instantMs > previousInstant && item.requestedDate > previousDate);
        previousInstant = item.instantMs;
        previousDate = item.requestedDate;
      }
      return items;
    });
  }
}
