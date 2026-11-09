import {html, nothing} from 'lit';
import {displayPoints} from '../domain/point-allocation';
import type {AllocationEvidence} from '../domain/point-allocation';
import {familyMessage} from './family-messages';
import type {FamilyMessage} from './family-messages';
import type {Language} from './messages';

export type ParticipantName = Readonly<{id: string; name: string}>;

export function allocationDetails(evidence: AllocationEvidence, language: Language,
  names: readonly ParticipantName[], preview = false) {
  const text = (key: FamilyMessage) => familyMessage(key, language);
  const points = (amount: number) => displayPoints(amount, language, evidence.precision);
  return html`<p>${text(evidence.mode)} · ${text(evidence.precision === 0 ? 'whole' : 'decimals')}
    ${evidence.rounding === null ? nothing : html` · ${text(evidence.rounding)}`}
    · ${text('revision')} ${evidence.policyRevision}
    · ${text(evidence.taskOverride ? 'taskPolicy' : 'householdPolicy')}</p>
    <dl><dt>${text('base')}</dt><dd>${displayPoints(evidence.base, language, evidence.base % 100 === 0 ? evidence.precision : 2)}</dd>
      <dt>${text(preview ? 'actualTotal' : 'total')}</dt><dd>${points(evidence.total)}</dd>
      ${evidence.shares.map(([id, amount]) => html`<dt>${names.find(person => person.id === id)?.name ?? id}</dt><dd>${points(amount)}</dd>`)}
    </dl>
    ${evidence.base === evidence.total ? nothing : html`<p>${text('difference')}</p>`}`;
}
