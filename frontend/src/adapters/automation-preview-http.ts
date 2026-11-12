import type {AutomationPreviewDraft, AutomationPreviewServer} from '../application/automation-preview';
import type {JournalContext} from '../domain/journal';
import {BoundedHTTP, readFailure} from './http-transport';
import type {FetchTransport} from './http-transport';
import {csrf} from './http-values';
import type {EntryEndpoint} from './http-values';
import {boolean, check, fields, integer} from './json-values';

function proposed(value: unknown, draft: AutomationPreviewDraft): boolean {
  const result = fields(value, ['version', 'trigger', 'task_title', 'would_create', 'conditions'], []);
  check(integer(result.version, 1) === 1 && result.trigger === 'manual' && result.task_title === draft.title);
  const matched = boolean(result.would_create);
  check(Array.isArray(result.conditions) && result.conditions.length === (draft.productId === null ? 0 : 1));
  if (draft.productId === null) check(matched);
  else {
    const condition = fields(result.conditions[0], ['path', 'kind', 'matched', 'product_id'], []);
    check(Array.isArray(condition.path) && condition.path.length === 0
      && condition.kind === 'stock_below_minimum' && condition.product_id === draft.productId
      && condition.matched === matched);
  }
  return matched;
}

export class HttpAutomationPreview implements AutomationPreviewServer {
  private readonly network: BoundedHTTP;
  constructor(target: EntryEndpoint, transport: FetchTransport) {this.network = new BoundedHTTP(target, transport);}

  access(context: JournalContext, householdId: string) {
    return this.network.owned(async signal => {
      const result = fields(await this.network.get('automation/preview-access', context, signal), ['household_id'], []);
      check(result.household_id === householdId);
    });
  }

  preview(context: JournalContext, draft: AutomationPreviewDraft) {
    return this.network.owned(async signal => {
      const token = csrf(await this.network.get('auth/csrf', context, signal));
      const body = JSON.stringify({version: 1, trigger: {kind: 'manual'},
        condition: draft.productId === null ? null : {kind: 'stock_below_minimum', product_id: draft.productId},
        action: {kind: 'task.create', title: draft.title}});
      const reply = await this.network.request('automation/preview', 'POST', context, body, null, token, signal);
      if (reply.status !== 200) readFailure(reply.status, reply.value);
      return proposed(reply.value, draft);
    });
  }
}
