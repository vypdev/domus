# Household administration

The current development backend supports public aliases and owner-private preferences in both
native Home Assistant Ingress and standalone deployments. It also exposes a bounded verified-name
roster and current-authorized directory facts. The complete administration workspace remains under
development. Installed owner Edge.5 is unchanged;
this source work does not publish a release or upgrade an installation.

Use the existing verified session. With the appropriate current permission, an API client can read
the public presentation, then submit its revision and an explicit alias. Null removes an alias;
literal text remains presentation only and never changes identity or permissions. The absence of a
saved alias does not fabricate a verified HA name or avatar.

Own preferences start with locale null (follow the browser, then English) and routine summaries
enabled. Save an explicit English/Spanish choice or null, the summary boolean and the independent
preference revision. Another household administrator cannot edit or recover your private
preferences. Saving the summary choice currently means saved with notification delivery unavailable;
it sends no message.

The roster keeps the existing membership and alias when HA metadata is absent, denied or unavailable.
A missing name receives an unavailable representation. Matching names never merge accounts. Metadata
contains a name and source state without another member's masked HA identifier, eligibility or
private preferences. Avatar delivery is unavailable; the adapter does not fetch external pictures.
The policy directory lists only currently source-eligible accounts and requires current policy
authority. Unavailable/denied source facts produce an explicit state, rather than a verified empty list.

Standalone access uses the signed-in account's grant. When HA denies directory access, an independently
verified own name can remain available. Native access never treats the Supervisor credential's own
account as the participant. Both deployments check current identity and local authority after source
I/O, so a late response cannot restore access lost during that read. These API/provider-fixture controls
do not establish a live owner-HA roster or the complete browser workspace.

If a response is lost, preserve the original action and request key. Use the protected original
lookup rather than submitting another mutation. A recovered receipt explains original processing;
after restoration its effect can be absent from current state. A stale revision, lost permission or
temporary HA outage does not authorize a retry or rebase. Review current state before deciding on
new work. An unexpired existing session may retain local reads during a temporary HA outage, while
changes remain blocked.

See the [API contract](household-api.md), [architecture](architecture-household-administration.md)
and [migration/rollback limits](household-administration-migration.md). The original
[72-case administration contract](../specs/household-administration.md),
[integration refinements](../specs/household-administration-integration.md) and
[workspace continuation](../specs/household-administration-workspace.md) remain required.
