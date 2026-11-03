# Household administration operations

The development workspace supports both native Ingress and standalone deployments. Ingress uses
its verified Home Assistant session; standalone uses the existing Home Assistant sign-in flow.
Each person needs a separate Home Assistant account. A display name or Domus alias never grants access.
This source increment does not update an installed application or publish a Stable/Edge release.

## Current access and data

The workspace verifies identity and household access before displaying administration. It hides
private forms while checking access and when a session expires or its participant changes. The
stored profile and the effective profile for the current session are shown separately: HA mapping
can make these different. Technical details show the server's current permission set.

A read-only outage lease permits available local reads and authorized original-result checks until
its existing deadline. It does not permit configuration changes or extend that deadline. A missing
roster does not prevent reading an independently permitted own alias. HA names can be available,
confirmed absent, denied or unavailable; an unavailable name or avatar is never invented.

## Review a change

Choose an available edit, adjust values, select **Review changes**, and inspect the confirmation
before **Save changes**. Participant edits identify the participant and stable membership reference.
Household settings, access policy, member configuration, public alias and private preferences each
keep their own original revision. An unrelated edit does not replace that revision.

A pending member starts the editor with a restricted profile. Activating that member requires an
explicit access confirmation. An administrator can adjust ordinary permissions by profile or member;
protected administration permissions cannot be edited. Inherited settings are preserved unless
explicitly changed. The HA mapping editor preserves its stored target when current directory or
membership facts cannot support a new selection. The server verifies eligibility and a remaining
administrator; names alone cannot prove either.

An optional alias changes public presentation only. The default uses an available HA name. Only the
participant can save their private locale and routine-summary preference. Saving summaries currently
sends no notification. A saved English/Spanish locale overrides the browser; an unset locale follows
the browser with English fallback. The header's language choice is temporary and sends no mutation.

A draft retains its original revision through translation, same-participant refresh and a rejected
preflight. **Reset from current data** explicitly adopts fresh values and revision. If the data that
permit viewing a draft become unavailable, its fields and confirmation are hidden until they can be
read again. Losing only write access leaves readable values inspectable and disables saving. A
participant/account/installation/channel change, logout or component retirement clears private drafts.

## An unknown result

The administration journal is separate from entry/setup recovery. It holds at most eight requests
and 65,536 bytes across contexts for one hour. It preserves the original action, payload, key and
revision before sending. Storage does not grant permission to inspect a result.

Use **Check original request** deliberately. It performs a protected original key/operation GET;
it does not resubmit a mutation, silently adopt a newer revision or replace unresolved work. Closing
an editor does not undo a server effect. A resolved record can be hidden locally without deleting
server history. An unresolved record cannot be dismissed to bypass this protection.

A conflict found during preflight can stop before any HTTP mutation or original record exists.
Review its access/data notice and reset explicitly when appropriate. A processed receipt describes
original processing; it does not guarantee that later state still has that effect. After restoring
a snapshot, historical processing can be retained while the original effect is absent. Inspect current
facts before requesting new work. Do not use a historical receipt to repopulate private preferences.

## Verification and rollout

Run `pnpm test:frontend` for actual Chromium component/controller coverage and its independent source
inventory audit. Run `pnpm build:frontend`, build the backend wheel, and run `pnpm test:frontend-entry`
for the compiled browser with disposable Python/SQLite Ingress and standalone fixtures. These fixtures
use fictional HA accounts and cannot establish owner-HA adoption.

Run `pnpm build:frontend-catalog` and `pnpm test:frontend-catalog` for the built entry and administration
catalog, including English/Spanish, keyboard focus, inert text, narrow layout and both color schemes.
Catalog stories explicitly emit intents without a server. They do not fabricate successful operations.
The owning SDD acceptance audit and required human UX review remain separate gates. Before owner rollout,
verify the exact package, both CPU images and compatible data/rollback procedure. Preserve the installed
owner Edge.5 and Edge.3 rollback until that adoption is verified.
