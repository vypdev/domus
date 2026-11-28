/** Project the task wire contract into immutable UI facts, preserving exact integers. */
import {nextRevision} from '../domain/administration';
import {civilDate} from '../domain/civil-date';
import {categoryLabel, isCategoryCommand, taskCommand, taskIdentifier, taskQuantity, taskText, TASK_PRIORITIES, TASK_STATES, TASK_TEXT_LIMITS, TASK_MATERIAL_STATES} from '../domain/tasks';
import type {TaskCategoryCatalog, TaskCommand, TaskCycleSummary, TaskDetail, TaskMaterialOutcome, TaskPage, TaskReceipt, TaskSummary, TaskMaterialCycle, TaskMaterialHistory} from '../domain/tasks';
import type {TaskOriginal, TaskRequest} from '../application/task-ports';
import {boolean, check, choice, fields, identifier, invalid, responseInteger, responseRevision, text} from './json-values';

function literal(value: unknown, maximum: number, required = true, multiline = false): string {
  try {return taskText(value, maximum, required, multiline);} catch {return invalid();}
}
function ids(value: unknown, maximum = 32): readonly string[] {
  check(Array.isArray(value) && value.length <= maximum);
  const result = value.map(identifier); check(new Set(result).size === result.length); return Object.freeze(result);
}
export function taskTimestamp(value: unknown): string {
  try {return responseRevision(value);} catch {check(responseInteger(value) === 0); return '0';}
}
function nullableId(value: unknown): string | null {return value === null ? null : identifier(value);}
function nullableTime(value: unknown): string | null {return value === null ? null : taskTimestamp(value);}
function summary(value: unknown): TaskSummary {
  const item = fields(value, ['occurrence_id', 'definition_id', 'definition_revision', 'title', 'state', 'revision', 'assignee_ids', 'due_at', 'current_cycle_id'], ['due_date']);
  const dueAt = nullableTime(item.due_at), dueDate = item.due_date ?? null;
  check(dueDate === null || (dueAt === null && civilDate(dueDate)));
  return Object.freeze({occurrenceId: identifier(item.occurrence_id), definitionId: identifier(item.definition_id),
    definitionRevision: responseRevision(item.definition_revision), title: literal(item.title, 160), state: choice(item.state, TASK_STATES),
    revision: responseRevision(item.revision), assigneeIds: ids(item.assignee_ids), dueAt, currentCycleId: nullableId(item.current_cycle_id),
    ...(dueDate === null ? {} : {dueDate})});
}
export function taskPage(value: unknown): TaskPage {
  const item = fields(value, ['items', 'next_cursor'], []); check(Array.isArray(item.items) && item.items.length <= 25);
  const items = item.items.map(summary); check(new Set(items.map(item => item.occurrenceId)).size === items.length);
  return Object.freeze({items: Object.freeze(items), nextCursor: item.next_cursor === null ? null : text(item.next_cursor, 512)});
}
function cycle(value: unknown, occurrenceId: string, householdId?: string): TaskCycleSummary {
  const item = fields(value, ['cycle_id', 'household_id', 'occurrence_id', 'recorded_by', 'performers', 'rules',
    'definition_revision', 'task_policy_revision', 'identity_policy_revision', 'performed_at', 'recorded_at', 'verification',
    'verified_by', 'verified_at', 'verification_reason', 'closed_at', 'revision'], []);
  check(identifier(item.occurrence_id) === occurrenceId); const household = identifier(item.household_id);
  check(householdId === undefined || householdId === household); responseRevision(item.revision);
  check(Array.isArray(item.performers) && item.performers.length >= 1 && item.performers.length <= 32);
  const performers = item.performers.map(raw => {const performer = fields(raw, ['member_id', 'role'], []);
    choice(performer.role, ['administrator', 'adult', 'restricted', 'viewer']); return identifier(performer.member_id);});
  check(new Set(performers).size === performers.length);
  return Object.freeze({cycleId: identifier(item.cycle_id), verification: choice(item.verification, ['none', 'pending', 'approved', 'rejected']),
    performedAt: taskTimestamp(item.performed_at), performerIds: Object.freeze(performers)});
}
const actions = ['claim', 'complete', 'approve', 'reject', 'reopen', 'assign', 'dependencies.update',
  'materials.settle',
  ...TASK_STATES.map(state => 'transition:' + state)];
export function taskDetail(value: unknown, occurrenceId: string, householdId: string): TaskDetail {
  const item = fields(value, ['work', 'rules', 'task_policy_revision', 'requirements', 'cycle', 'allowed_actions', 'consumer_delivery',
    'materials', 'dependency_reviews', 'dependency_review_required'], ['completion_points']);
  check(item.consumer_delivery === 'unconfirmed');
  const work = fields(item.work, ['occurrence_id', 'household_id', 'definition_snapshot', 'created_at', 'state', 'revision',
    'assignee_ids', 'prerequisite_ids', 'required_subtask_ids', 'due_at', 'current_cycle_id', 'current_cycle_revision', 'state_reason'], ['due_date']);
  check(identifier(work.occurrence_id) === occurrenceId && identifier(work.household_id) === householdId);
  const definition = fields(work.definition_snapshot, ['definition_id', 'household_id', 'content', 'created_at', 'overrides', 'state', 'revision', 'materials'], ['category_label']);
  check(identifier(definition.household_id) === householdId);
  const content = fields(definition.content, ['title', 'description', 'priority', 'tags'], ['category_id']);
  const categoryId = nullableId(content.category_id ?? null), capturedLabel = definition.category_label ?? null;
  check((categoryId === null) === (capturedLabel === null));
  const displayCategory = capturedLabel === null ? null : literal(capturedLabel, 80);
  const rules = fields(item.rules, ['claim_allowed', 'eligible_roles', 'verification', 'adult_performer_may_approve',
    'task_scoped_material_consumption', 'material_recording', 'point_value_minor', 'dependency_gate'], []);
  const base = summary({occurrence_id: work.occurrence_id, definition_id: definition.definition_id, definition_revision: definition.revision,
    title: content.title, state: work.state, revision: work.revision, assignee_ids: work.assignee_ids, due_at: work.due_at,
    due_date: work.due_date, current_cycle_id: work.current_cycle_id});
  check(Array.isArray(item.allowed_actions) && item.allowed_actions.length <= actions.length);
  const allowedActions = item.allowed_actions.map(raw => choice(raw, actions)); check(new Set(allowedActions).size === allowedActions.length);
  check(Array.isArray(definition.materials) && definition.materials.length <= 32);
  const materials = definition.materials.map(raw => {
    const line = fields(raw, ['line_id', 'binding', 'planned_quantity'], []);
    const binding = fields(line.binding, ['household_id', 'reference_id', 'product_id', 'unit_id', 'location_id', 'revision', 'precision', 'label'], []);
    check(identifier(binding.household_id) === householdId);
    let quantity: string; try {quantity = taskQuantity(line.planned_quantity);} catch {return invalid();}
    const precision = responseInteger(binding.precision); check(precision <= 6 && (quantity.split('.')[1]?.length ?? 0) <= precision);
    return Object.freeze({lineId: identifier(line.line_id), label: literal(binding.label, 160, false), plannedQuantity: quantity, precision,
      unitId: identifier(binding.unit_id), locationId: identifier(binding.location_id)});
  });
  check(new Set(materials.map(material => material.lineId)).size === materials.length);
  check(Array.isArray(item.materials) && item.materials.length <= 32);
  const materialOutcomes = item.materials.map(taskMaterialOutcome);
  check(new Set(materialOutcomes.map(value => value.intentId)).size === materialOutcomes.length);
  check(new Set(materialOutcomes.map(value => value.lineId)).size === materialOutcomes.length);
  const pendingMaterials = materialOutcomes.some(value => value.state.startsWith('pending_'));
  const current = item.cycle === null ? null : cycle(item.cycle, occurrenceId, householdId);
  check(base.currentCycleId === null || current?.cycleId === base.currentCycleId);
  check(materialOutcomes.every(value => current?.cycleId === value.cycleId && materials.some(line => line.lineId === value.lineId)));
  return Object.freeze({...base, description: literal(content.description, 4000, false, true), priority: choice(content.priority, TASK_PRIORITIES),
    ...base.state === 'blocked' ? {stateReason: literal(work.state_reason, TASK_TEXT_LIMITS.reason, true, true)} : {},
    allowedActions: Object.freeze(allowedActions), cycle: current, materials: Object.freeze(materials), materialOutcomes: Object.freeze(materialOutcomes),
    ...item.completion_points === undefined ? {} : {completionPoints: choice(item.completion_points, ['automatic','manual','manager_required'] as const)},
    materialRecording: choice(rules.material_recording, ['review_on_completion', 'separate_recording']),
    dependencyReviewRequired: boolean(item.dependency_review_required), pendingMaterials, categoryLabel: displayCategory});
}
function nullableQuantity(value: unknown): string | null {
  if (value === null) return null;
  try {return taskQuantity(value);} catch {return invalid();}
}
export function taskMaterialOutcome(raw: unknown): TaskMaterialOutcome {
  const value = fields(raw, ['intent_id', 'cycle_id', 'line_id', 'submitted_quantity', 'quantity', 'state', 'pending_reason', 'movement_id',
    'effect_revision', 'revision', 'message', 'action_required', 'confirmed_quantity', 'confirmed_effect_revision', 'posted_at'], []);
  text(value.message, 2048); if (value.action_required !== null) text(value.action_required, 4096);
  const pendingReason = value.pending_reason === null ? null : choice(value.pending_reason, ['actual_quantity_required',
    'material_permission_required', 'explicit_settlement_required', 'awaiting_inventory_confirmation', 'inventory_unavailable',
    'insufficient_stock', 'inventory_binding_changed', 'inventory_location_archived']);
  return Object.freeze({intentId: identifier(value.intent_id), cycleId: identifier(value.cycle_id), lineId: identifier(value.line_id),
    revision: responseRevision(value.revision), effectRevision: responseRevision(value.effect_revision),
    submittedQuantity: nullableQuantity(value.submitted_quantity), quantity: nullableQuantity(value.quantity),
    state: choice(value.state, TASK_MATERIAL_STATES), pendingReason, movementId: nullableId(value.movement_id),
    confirmedQuantity: nullableQuantity(value.confirmed_quantity),
    confirmedEffectRevision: value.confirmed_effect_revision === null ? null : responseRevision(value.confirmed_effect_revision),
    postedAt: nullableTime(value.posted_at)});
}
export function taskMaterialCycle(raw: unknown, work: TaskDetail, householdId: string, expectedCycleId?: string): TaskMaterialCycle {
  const value = fields(raw, ['occurrence_id','cycle','materials','allowed_actions'], []);
  check(identifier(value.occurrence_id) === work.occurrenceId);
  const selected = cycle(value.cycle, work.occurrenceId, householdId);
  check(expectedCycleId === undefined || selected.cycleId === expectedCycleId);
  const closedAt = nullableTime((value.cycle as {closed_at:unknown}).closed_at);
  check(Array.isArray(value.materials) && value.materials.length <= 32);
  const outcomes = value.materials.map(taskMaterialOutcome);
  check(new Set(outcomes.map(item => item.intentId)).size === outcomes.length
    && new Set(outcomes.map(item => item.lineId)).size === outcomes.length);
  check(outcomes.every(item => item.cycleId === selected.cycleId && work.materials.some(line => line.lineId === item.lineId)));
  check(Array.isArray(value.allowed_actions) && value.allowed_actions.length <= 1);
  const allowedActions = value.allowed_actions.map(item => choice(item, ['materials.settle'] as const));
  return Object.freeze({cycle:selected, closedAt, materialOutcomes:Object.freeze(outcomes), allowedActions:Object.freeze(allowedActions)});
}
export function taskMaterialHistory(raw: unknown, work: TaskDetail, householdId: string): TaskMaterialHistory {
  const value = fields(raw, ['items','next_cursor'], []);
  check(Array.isArray(value.items) && value.items.length <= 1);
  const items = value.items.map(item => taskMaterialCycle(item, work, householdId));
  check(items.every(item => item.closedAt !== null));
  return Object.freeze({items:Object.freeze(items), nextCursor:value.next_cursor === null ? null : text(value.next_cursor,512)});
}
function category(value: unknown) {
  const row = fields(value, ['category_id', 'household_id', 'label', 'revision', 'archived'], []);
  const label = literal(row.label, 80);
  check(label === categoryLabel(label));
  return Object.freeze({id: identifier(row.category_id), householdId: identifier(row.household_id),
    label, revision: responseRevision(row.revision), archived: boolean(row.archived)});
}
export function taskCategoryCatalog(value: unknown, householdId: string): TaskCategoryCatalog {
  const item = fields(value, ['categories', 'can_manage'], []);
  check(Array.isArray(item.categories) && item.categories.length <= 100);
  const categories = item.categories.map(raw => {
    const {householdId: home, archived, ...selected} = category(raw);
    check(!archived && home === householdId); return Object.freeze(selected);
  });
  check(new Set(categories.map(item => item.id)).size === categories.length);
  return Object.freeze({categories: Object.freeze(categories), canManage: boolean(item.can_manage)});
}
function originalBasePoints(raw: unknown, expected: number | undefined) {
  if (expected === undefined) return {};
  check(responseInteger(raw) === expected);
  return {basePointsMinor: expected};
}
export function taskReceipt(value: unknown, request: TaskRequest | TaskOriginal, lookup: boolean): TaskReceipt {
  const command = request.command, categoryCommand = isCategoryCommand(command);
  const item = fields(value, ['state', 'archived_by', 'operation_id', 'created_at', 'result', 'message', 'action_required',
    ...lookup ? ['action', 'command_key', ...categoryCommand ? [] : ['delivery']] : []], []);
  text(item.message, 2048); text(item.action_required, 4096); taskTimestamp(item.created_at);
  const stage = choice(item.state, ['committed', 'historical']), archivedBy = nullableId(item.archived_by), operationId = identifier(item.operation_id);
  const schedule = command.action === 'task.create' ? command.payload.schedule : undefined;
  const basePoints = command.action === 'task.create' ? command.payload.overrides?.point_value_minor : undefined;
  const pointFields = basePoints === undefined ? [] : ['point_value_minor'];
  check(stage !== 'historical' || archivedBy !== null);
  if (lookup) {
    const action = schedule === undefined ? command.action : 'recurrence.' + schedule.draft.kind + '.create';
    check(item.action === action && item.command_key === request.key);
    const known = (request as TaskOriginal).operationId; check(known === null || known === operationId);
    if (!categoryCommand) {
      const delivery = choice(item.delivery, ['pending', 'delivered', 'suppressed']);
      check(stage === 'historical' ? delivery === 'suppressed' : delivery !== 'suppressed');
    }
  }
  if (categoryCommand) {
    const selected = category(item.result);
    check(selected.revision === (command.action === 'task.category.create' ? '1' : nextRevision(command.payload.expected_revision)));
    check(command.action === 'task.category.create' || command.categoryId === selected.id);
    check(selected.archived === (command.action === 'task.category.archive'));
    if (command.action !== 'task.category.archive') check(selected.label === categoryLabel(command.payload.label));
    return Object.freeze({kind: 'receipt', stage, action: command.action, operationId,
      occurrenceId: null, revision: selected.revision, state: selected.archived ? 'archived' : 'active', cycle: null, archivedBy});
  }
  if (schedule !== undefined) {
    const result = fields(item.result, ['schedule_id', 'definition_id', 'revision', 'pattern_revision',
      'state', 'processing', 'first_occurrence_id', ...pointFields], []);
    identifier(result.schedule_id); identifier(result.definition_id);
    const revision = responseRevision(result.revision);
    check(revision === '1' && responseRevision(result.pattern_revision) === '1'
      && result.state === 'active' && result.processing === 'pending' && result.first_occurrence_id === null);
    return Object.freeze({kind: 'receipt', stage, action: 'task.create', operationId,
      occurrenceId: null, revision, state: 'active', cycle: null, archivedBy, ...originalBasePoints(result.point_value_minor, basePoints)});
  }
  if (command.action === 'task.material.settle') {
    const result = fields(item.result, ['definition_id', 'definition_revision', 'occurrence_id', 'revision', 'state', 'assignee_ids',
      'state_reason', 'prerequisite_ids', 'required_subtask_ids', 'cycle', 'consumer_delivery', 'material', 'material_source', 'material_action'], []);
    const occurrenceId = identifier(result.occurrence_id);
    check(occurrenceId === command.occurrenceId && result.consumer_delivery === 'unconfirmed' && result.material_action === command.payload.action);
    identifier(result.definition_id); responseRevision(result.definition_revision); responseRevision(result.revision); choice(result.state, TASK_STATES);
    ids(result.assignee_ids); ids(result.prerequisite_ids, 64); ids(result.required_subtask_ids, 64); literal(result.state_reason, TASK_TEXT_LIMITS.reason, false, true);
    const savedCycle = cycle(result.cycle, occurrenceId), material = taskMaterialOutcome(result.material);
    const source = fields(result.material_source, ['household_id', 'occurrence_id', 'cycle_id', 'intent_id', 'line_id', 'definition_revision', 'performer_ids'], []);
    identifier(source.household_id);
    check(material.intentId === command.intentId && material.cycleId === command.payload.cycle_id && savedCycle.cycleId === material.cycleId
      && BigInt(material.revision) >= BigInt(command.payload.expected_revision)
      && source.occurrence_id === occurrenceId && source.cycle_id === material.cycleId && source.intent_id === material.intentId && source.line_id === material.lineId
      && responseRevision(source.definition_revision) === responseRevision(result.definition_revision)
      && JSON.stringify(ids(source.performer_ids)) === JSON.stringify(savedCycle.performerIds));
    const savedHome = fields(result.cycle, ['cycle_id', 'household_id', 'occurrence_id', 'recorded_by', 'performers', 'rules',
      'definition_revision', 'task_policy_revision', 'identity_policy_revision', 'performed_at', 'recorded_at', 'verification',
      'verified_by', 'verified_at', 'verification_reason', 'closed_at', 'revision'], []);
    check(savedHome.household_id === source.household_id && responseRevision(savedHome.definition_revision) === responseRevision(source.definition_revision));
    if (command.payload.action === 'correct') check(material.quantity === command.payload.quantity);
    return Object.freeze({kind: 'receipt', stage, action: command.action, operationId, occurrenceId, intentId: material.intentId,
      material, cycle: savedCycle, archivedBy});
  }
  const result = fields(item.result, ['definition_id', 'definition_revision', 'occurrence_id', 'revision', 'state', 'assignee_ids', 'state_reason', 'prerequisite_ids', 'required_subtask_ids', ...pointFields],
    ['cycle', 'consumer_delivery', 'materials', 'compensates_cycle_id', 'dependency_review_required']);
  const occurrenceId = identifier(result.occurrence_id), revision = responseRevision(result.revision), state = choice(result.state, TASK_STATES);
  identifier(result.definition_id); responseRevision(result.definition_revision);
  const assigneeIds = ids(result.assignee_ids);
  ids(result.prerequisite_ids, 64); ids(result.required_subtask_ids, 64);
  check(revision === (command.action === 'task.create' ? '1' : nextRevision(command.payload.expected_revision)));
  if (command.action !== 'task.create') check(command.occurrenceId === occurrenceId);
  if (command.action === 'task.assign')
    check(JSON.stringify([...assigneeIds].sort()) === JSON.stringify([...command.payload.assignee_ids].sort()));
  if (command.action === 'task.transition')
    check(state === command.payload.target
      && literal(result.state_reason, TASK_TEXT_LIMITS.reason, state === 'blocked', true) === command.payload.reason);
  const savedCycle = Object.hasOwn(result, 'cycle') ? cycle(result.cycle, occurrenceId) : null;
  if (command.action === 'task.complete') {
    check(state === 'completed' && savedCycle !== null && savedCycle.performedAt === command.payload.performed_at
      && JSON.stringify([...savedCycle.performerIds].sort()) === JSON.stringify([...command.payload.performer_ids].sort()));
  }
  if (command.action === 'task.verify' || command.action === 'task.reopen') {
    check(savedCycle?.cycleId === command.payload.cycle_id);
    if (command.action === 'task.verify') check(savedCycle.verification === command.payload.decision);
    else check(result.compensates_cycle_id === command.payload.cycle_id && result.dependency_review_required === true);
  }
  return Object.freeze({kind: 'receipt', stage, action: command.action, operationId, occurrenceId, revision, state, cycle: savedCycle, archivedBy,
    ...command.action === 'task.assign' ? {assigneeIds} : {},
    ...command.action === 'task.transition' ? {stateReason: command.payload.reason} : {},
    ...originalBasePoints(result.point_value_minor, basePoints)});
}
/** Only validated decimal lexemes bypass JSON's string quoting; arbitrary text always uses JSON.stringify. */
export function taskCommandBody(value: TaskCommand): string {
  const command = taskCommand(value); check(command !== undefined);
  if (command.action === 'task.complete') {
    const {expected_revision, performed_at, ...rest} = command.payload;
    return '{"expected_revision":' + expected_revision + ',"performed_at":' + performed_at + ',' + JSON.stringify(rest).slice(1);
  }
  if (command.action === 'task.create' && command.payload.schedule !== undefined) {
    const {title, description, priority, category_id, overrides, materials, schedule} = command.payload;
    const {kind: _, ...draft} = schedule.draft;
    const {revision, ...policy} = schedule.policy;
    const fields = JSON.stringify({task: {title, description, priority, category_id, overrides, materials}, ...draft, policy});
    return fields.slice(0, -2) + ',"revision":' + revision + '}}';
  }
  const {expected_revision, ...rest} = command.payload;
  return '{"expected_revision":' + expected_revision + (Object.keys(rest).length ? ',' + JSON.stringify(rest).slice(1) : '}');
}
export function taskRequest(value: unknown, lookup: false): TaskRequest;
export function taskRequest(value: unknown, lookup: true): TaskOriginal;
export function taskRequest(value: unknown, lookup: boolean): TaskRequest | TaskOriginal {
  const item = fields(value, lookup ? ['key', 'command', 'operationId'] : ['key', 'command'], []);
  const key = identifier(item.key), command = taskCommand(item.command); check(command !== undefined);
  if (!lookup) return Object.freeze({key, command});
  return Object.freeze({key, command, operationId: item.operationId === null ? null : taskIdentifier(item.operationId)});
}
