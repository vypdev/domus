# Household administration

The current development backend supports public aliases and owner-private preferences in both
native Home Assistant Ingress and standalone deployments. The complete administration workspace
and verified HA presentation metadata remain under development. Installed owner Edge.5 is unchanged;
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
