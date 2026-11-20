# Find household products by manually entered barcode

- Status: Draft
- Owners: Domus maintainers and Inventory
- Scope: Manual GTIN validation, local catalog search and barcode associations
- Open decisions blocking readiness: none

## 1. Executive summary

Enter the number printed under a retail barcode and find the corresponding
product in the household catalog. Inventory managers can associate a validated
number with an existing catalog product and correct an erroneous association.

## 2. Problem, current behavior, and evidence

Inventory supports product registration and stock workflows. Its catalog
has no local barcode associations or lookup. The owner confirmed manual
entry and local matching in the existing Inventory specification.

## 3. Actors, surfaces, and terminology

A household reader can search Inventory. A member with current inventory
management authority can maintain the association. A GTIN is the retail
trade item number printed alongside a barcode. The local association points
to the stable product identity.

## 4. Goals, non-goals, and fixed invariants

| Requirement | Behavior |
|---|---|
| stock-local-barcode-R01 | Accept manually entered GS1 GTIN-8, GTIN-12, GTIN-13 and GTIN-14 text, validate the check digit and use the zero-padded 14-character identity for matching. |
| stock-local-barcode-R02 | A current household reader can find at most one catalog product by a valid barcode. Distinguish invalid input, an unlinked barcode and an unavailable lookup. Keep requests within Domus. |
| stock-local-barcode-R03 | An inventory manager can link or explicitly remove a barcode association in the current household. Concurrent updates preserve uniqueness. Original operations can be recovered. Product identity, quantities and existing ledger history are preserved. |
| stock-local-barcode-R04 | Migrate and restore the local association index safely. Preserve representative older inventory and its receipts. |
| stock-local-barcode-R05 | Support an accessible manual workflow in English and Spanish through both deployment compositions and the installed Edge candidate. |

The manual workflow forms the local lookup shared by future camera and
configured provider adapters. Package quantities follow the owning conversion
contract.

## 5. Current versus proposed product journey

Open Inventory, type or paste a GTIN, and search. If a product matches, see
its name and open its existing stock detail. When there is no association,
a manager can attach the code to an existing product. Ordinary product
registration remains available.

## 6. Functional behavior and state model

Validate ASCII digits, the supported lengths and the GS1 check digit before
deriving the canonical string. Preserve leading zeroes. Apply the same
canonical identity to every lookup and association. Equivalent forms
resolve the same link. A code belongs to at most one product in a household.
Remove a link only when it is still the association the manager reviewed.
Link changes and their original command receipts commit atomically.

## 7. User-facing configuration

Use the existing household locale and inventory grants. The lookup reads
the current household database and uses existing Inventory navigation.

## 8. Clean Architecture design

A pure domain value validates the GTIN. Application services own grants,
association commands and exact queries. SQLite enforces the household key
and the product reference. The HTTP entry point validates transport input.
The browser uses published ha-ui field, button and feedback components.

## 9. UI/UX and content contract

Label the field for the printed barcode digits, preserve zeroes when
pasting and use a numeric keyboard hint. Give an example of the supported
lengths. State whether the code is invalid, unlinked, found or temporarily
unavailable and offer the relevant next action. Show the product name before
the manager submits a link or removal. Preserve a correctable draft.

## 10. Failure, recovery, and cleanup

A duplicate association displays the conflict while retaining the entered
code. An unavailable query offers retry. A lost successful reply recovers the
original result. A stale removal leaves a newer association intact.

## 11. Security, permissions, and privacy

Authorize exact reads under the verified current household. Recheck
inventory management authority for writes and original receipt access.
Validate before querying and resolve products within the current household.
Keep lookup data within the Domus installation.

## 12. Observability and operational UX

Operation receipts record association changes. Product history continues to
report its existing movement identities and quantities.

## 13. Compatibility, migration, rollout, and rollback

Initialize an empty barcode index for existing households. Test
representative data from the current previous schema 34, schema 30 and schema 20. Verify restart and activated
compatible restore of a barcode link and its receipt. Qualify the installed
candidate with its exact version and a compatible rollback checkpoint.

## 14. Testing strategy and numeric budget

Minimum eight distinct cases.

| Area | Minimum distinct cases | Behaviors/risks covered |
|---|---:|---|
| Barcode identity | 1 | Observable scenarios in the case inventory. |
| Local catalog | 1 | Observable scenarios in the case inventory. |
| Authorization | 1 | Observable scenarios in the case inventory. |
| State and concurrency | 1 | Observable scenarios in the case inventory. |
| State and recovery | 1 | Observable scenarios in the case inventory. |
| Upgrade and restoration | 1 | Observable scenarios in the case inventory. |
| Browser acceptance | 1 | Observable scenarios in the case inventory. |
| Installed acceptance | 1 | Observable scenarios in the case inventory. |
| Total | 8 | Distinct inventory cases; repeated executions do not add cases. |

| Case ID | Area | Requirements | Scenario |
|---|---|---|---|
| stock-local-barcode-C01 | Barcode identity | stock-local-barcode-R01 | Validate GS1 check digits for all four supported lengths. Leading zeroes survive and equivalent strings resolve one canonical key. Reject malformed, wrong-length and check-digit-invalid input. |
| stock-local-barcode-C02 | Local catalog | stock-local-barcode-R02 | Find a linked product and distinguish a valid unlinked code. Exercise local lookup with external connectivity absent and observe only installation-local requests. |
| stock-local-barcode-C03 | Authorization | stock-local-barcode-R02, stock-local-barcode-R03 | A current household reader can find an own product. A foreign association is invisible. A reader without management access cannot modify a link or recover its original write. |
| stock-local-barcode-C04 | State and concurrency | stock-local-barcode-R03 | Race two products for equivalent forms of one code. Exactly one link wins. Explicitly remove it and verify a stale removal cannot delete a later association. |
| stock-local-barcode-C05 | State and recovery | stock-local-barcode-R03 | Recover the original receipt after a lost reply, reject a different command under the same key and roll back the association on a late failure. |
| stock-local-barcode-C06 | Upgrade and restoration | stock-local-barcode-R04 | Preserve representative schema 34, schema 30 and schema 20 data during migration. Restart and activate a compatible backup containing a link and its original operation. |
| stock-local-barcode-C07 | Browser acceptance | stock-local-barcode-R05 | Enter a code, see invalid and unlinked states, link to the selected product and find it again. Verify desktop keyboard and narrow touch use in English and Spanish through Ingress and standalone. |
| stock-local-barcode-C08 | Installed acceptance | stock-local-barcode-R05 | Verify the installed Edge version, exercise the manual lookup with disposable data and qualify both architecture images. |

## 15. Documentation and discoverability

[specs/stock-local-barcode.md](stock-local-barcode.md) · [docs/roadmap.md](../docs/roadmap.md) · [docs/household-api.md](../docs/household-api.md) · [backend/src/domus/domain/inventory.py](../backend/src/domus/domain/inventory.py) · [backend/src/domus/application/inventory.py](../backend/src/domus/application/inventory.py) · [backend/src/domus/application/inventory\_queries.py](../backend/src/domus/application/inventory_queries.py) · [backend/src/domus/infrastructure/sqlite\_inventory.py](../backend/src/domus/infrastructure/sqlite_inventory.py) · [backend/src/domus/entrypoints/inventory\_http.py](../backend/src/domus/entrypoints/inventory_http.py) · [frontend/src/presentation/domus-inventory.ts](../frontend/src/presentation/domus-inventory.ts) · [frontend/src/presentation/inventory-messages.ts](../frontend/src/presentation/inventory-messages.ts)

| Path | Change |
|---|---|
| specs/stock-local-barcode.md | create |
| docs/roadmap.md | update |
| docs/household-api.md | update |
| backend/src/domus/domain/inventory.py | update |
| backend/src/domus/application/inventory.py | update |
| backend/src/domus/application/inventory_queries.py | update |
| backend/src/domus/infrastructure/sqlite_inventory.py | update |
| backend/src/domus/entrypoints/inventory_http.py | update |
| frontend/src/presentation/domus-inventory.ts | update |
| frontend/src/presentation/inventory-messages.ts | update |

## 16. Acceptance scenarios

Enter a valid UPC, link it to an existing product, and look it up using its
zero-padded representation. Observe the product's stable identity and exact
stock. Correct the association through the manager flow.

## 17. Requirements traceability

| Requirement | Cases |
|---|---|
| stock-local-barcode-R01 | stock-local-barcode-C01 |
| stock-local-barcode-R02 | stock-local-barcode-C02, stock-local-barcode-C03 |
| stock-local-barcode-R03 | stock-local-barcode-C03, stock-local-barcode-C04, stock-local-barcode-C05 |
| stock-local-barcode-R04 | stock-local-barcode-C06 |
| stock-local-barcode-R05 | stock-local-barcode-C07, stock-local-barcode-C08 |

## 18. Implementation sequence

Validate and normalize GTINs. Add protected exact lookup, association
commands and durable storage. Integrate the manual Inventory experience
and qualify the package on both deployment targets.

## 19. Definition of Done

Verify the eight cases, global and per-file coverage, both architecture
images, deployed Edge version and scoped test cleanup.

## 20. References and decisions

The owner's decision A14 and household-inventory-R7 accept manual entry
and local catalog search. GS1 defines the supported GTIN lengths, check
digit and the 14-character zero-padded representation.

https://support.gs1.org/support/solutions/articles/43000734355-what-is-the-required-format-of-gtin-in-gs1-edi-standards-
https://ref.gs1.org/guidelines/2d-in-retail/1.1.0/
