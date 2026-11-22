# Shopping workspace implementation and acceptance map

- Status: Implementation note; qualification in progress
- Date: 2026-11-22
- Owner: application-experience
- Issue: [#162](https://github.com/vypdev/domus/issues/162)
- Normative contract: [Open Shopping as a direct household workspace](application-experience.md#proposed-change-open-shopping-as-a-direct-household-workspace)

This note explains the implementation of the published #162 unit. That unit
remains the sole owner of its eleven requirements and six acceptance cases.
References below identify those cases within that unit; they introduce no new
requirements, case inventory or acceptance counts. The earlier application and
entry-interface inventories retain their original scope and identities.

## Journey and responsibilities

The shared navigation adds **Shopping / Compras** between Family and Inventory.
It opens the current shared list, manual extras, purchases, store sessions and
physical receipts. **Inventory / Inventario** retains the catalog, Pantry,
locations, materials, stock movements and replenishment. Shopping provides a
contextual Inventory link for stock management.

`#shopping` opens the shared list. `#shopping/product:<id>` and
`#shopping/extra:<id>` focus the indicated current row. Previously shared
`#inventory-shopping/product:<id>` and `#inventory-shopping/extra:<id>` fragments
are aliases for the same Shopping destination. A missing item focuses the list
with an explanation. Unknown or malformed fragments retain the existing safe
Overview fallback and do not rewrite the URL or issue a command.

## State, architecture and recovery

Both mounted presentations use one `InventoryController`, protected HTTP adapter
and existing `InventorySessionJournal`. Destination and item selection are
presentation state, not authorization scope. A queued contextual read waits for
an owned command/read to finish. A canceled late navigation callback cannot
consume a replacement route. Navigation does not dispatch a domain mutation.

Same-member/household navigation retains form DOM, literal notes, priority,
selected session work and the original pending request. Refresh and recovery
remain explicit. **Check original operation / Consultar operación original**
reads the original key before any existing permitted resend; it never invents
a replacement key. The existing form submission fingerprint prevents an
unrelated original result from clearing a newer extra draft.

Failed reads retain only a last-loaded display projection and disable Shopping
mutations until a successful refresh. This projection is never substituted for
current controller authority. Denial removes private facts and distinguishes
an unresolved operation. Current server grants control readers, requesters,
shoppers and stock managers independently. Role/policy revisions revalidate
authority without pretending that the participant changed. A different verified
household/member/principal retires the prior protected view and owned pending
request; unconfirmed retirement closes the view. Logout uses the existing
protected-state cleanup. Unrelated browser storage remains untouched.

The persisted scope includes the verified household and member as well as the
installation, channel and HA subject, so owner validation also applies after a
reload. The packet slot, keys, canonical format and original request key remain
unchanged. A matching owner's pending packet is reopened byte-for-byte; an old
scope that cannot establish household/member ownership follows the existing
incompatible-scope retirement without a lookup, resend or replacement request.
Previously committed server receipts are unaffected. Failed retirement keeps
recovery and writes blocked rather than adopting the old request.

## Compatibility, configuration and limits

There is no backend, API, SQLite schema, ledger or receipt-format change.
Schema 37 and exact published `@vypdev/ha-ui@0.1.0-next.5` remain the cohort.
No new configuration or notification is introduced. Existing command limits,
permissions, server audit, storage failure handling and restore rules apply.
The presentation move does not authorize Stable publication or deployment.
Qualification uses Edge, both real CPU images and both deployment base paths.
Rollback uses the prior compatible binary and retained state, without replaying
or canceling effects.

## Acceptance and evidence

| Owning-unit reference | Observable checks and evidence |
| --- | --- |
| `inventory1-C01` | Distinct surfaces, localized tab/heading/focus, repeated activation, narrow touch/overflow and wide keyboard in both themes. |
| `inventory1-C02` | Direct/reload/history, Overview and legacy item entry, missing items and malformed fallback without writes. |
| `inventory1-C03` | Literal drafts, priority, selected work and original request across destinations; recovery preserves unrelated work and creates one effect. |
| `inventory1-C04` | Current reader/requester/shopper/stock grants, loading/empty/unavailable/denied/stale/pending/committed/conflict and revocation. |
| `inventory1-C05` | Logout and verified ownership changes retire drafts/recovery; failed retirement closes access. |
| `inventory1-C06` | Source coverage, actual amd64/ARM64 and installed Edge, restart/restore, ledger/receipt/schema/package compatibility. |

The new [browser campaign](../frontend/tests/e2e/shopping-workspace-navigation.spec.ts)
executes twelve deployment variants of these six cases. Existing full Shopping,
receipt, stock and annotation journeys remain and use the appropriate real
workspace. Controller/component/page tests cover request ownership, queued-read
races, denied/stale projections and owner retirement, including storage failure.
The [qualification record](../docs/evidence/shopping-workspace-navigation-qualification.md)
and its [machine-readable evidence](../docs/evidence/shopping-workspace-navigation.json)
distinguish executed checks from remaining acceptance gates. Declared tests,
source inspection and catalog generation do not prove installed acceptance.

The catalog registers this implementation note under application-experience.
Its owner remains proposed with wider integrated acceptance still open. The
unmodified SDK catalog entrypoint validates reciprocal paths and renders the
generated view; the qualification records the actual invocation because this
checkout declares no `validate:specifications` package script. The native owning
unit and its retained prefix are preserved. Final acceptance requires the whole
published Definition of Done, same-head checks, review and installed evidence.
