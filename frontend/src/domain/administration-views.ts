/** Verified server facts remain presentation input; these values never grant backend authority. */
import type {Revision, OwnPreferenceValues} from './administration';
import type {AdministrationCommand, MemberRole, MemberStatus, PermissionDecision, ProfileDecision, MAPPING_MODES} from './administration-commands';
import type {Authorization} from './entry';

export type AdministrationAction = AdministrationCommand['action'];
export type MappingMode = typeof MAPPING_MODES[number];
export type MetadataState = 'available' | 'absent' | 'denied' | 'unavailable';
export type DirectoryState = Exclude<MetadataState, 'absent'>;
export interface AdministrationMember {
  readonly memberId: string; readonly role: MemberRole; readonly status: MemberStatus;
  readonly revision: Revision; readonly haUserId: string | null; readonly exceptions: readonly PermissionDecision[] | null;
}
export interface AdministrationAccess extends Authorization {
  readonly member: AdministrationMember | null; readonly effectiveRole: MemberRole | null; readonly policyRevision: Revision | null;
}
export interface PublicPresentation {readonly memberId: string; readonly alias: string | null; readonly revision: Revision;}
export interface OwnPreferences extends OwnPreferenceValues {
  readonly memberId: string; readonly revision: Revision; readonly notificationDelivery: 'unavailable';
}
export interface RosterMember {
  readonly member: AdministrationMember; readonly presentation: PublicPresentation;
  readonly metadata: Readonly<{state: MetadataState; name: string | null; avatarState: 'unavailable'}>;
}
export interface Roster {readonly members: readonly RosterMember[]; readonly directoryState: DirectoryState;}
export interface Directory {
  readonly state: DirectoryState; readonly profiles: readonly Readonly<{haUserId: string; name: string | null}>[];
}
export interface AdministrationPolicy {
  readonly householdId: string; readonly revision: Revision; readonly mappingMode: MappingMode;
  readonly targetHAUserId: string | null; readonly adjustments: readonly ProfileDecision[];
}
export interface AdministrationCapabilities {
  readonly contractVersion: 2; readonly householdId: string; readonly actions: readonly AdministrationAction[];
}
export type AdministrationResult = Readonly<{revision: Revision}> & (
  Readonly<{householdId: string; mappingMode?: MappingMode}>
  | Readonly<{memberId: string; role: MemberRole; status: MemberStatus}>
  | Readonly<{memberId: string; alias: string | null}>
  | OwnPreferences);
export interface AdministrationReceipt {
  readonly kind: 'receipt'; readonly stage: 'committed' | 'historical'; readonly action: AdministrationAction;
  readonly operationId: string; readonly archivedBy: string | null; readonly createdAt: number;
  readonly result: AdministrationResult; readonly notificationDelivery: 'unavailable';
  readonly eventDelivery: 'pending' | 'delivered' | 'suppressed' | null;
}
