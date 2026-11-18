# Home Assistant shopping list qualification

[Domus #132](https://github.com/vypdev/domus/issues/132) defines the
[shared shopping list projection](../../specs/home-assistant-surface.md#show-the-shared-shopping-list-in-home-assistant).
The [companion setup](../tasks/ha-shopping-list.md) documents the installation grant
and the native read-only entity.

| Case | Verification |
| --- | --- |
| ha-shopping-list-C01 | Backend fixtures on Ingress and standalone compare the native snapshot with Overview using a tracked product, a reservation, an outstanding purchase and manual extras. Receipts remain a separate Domus workflow. |
| ha-shopping-list-C02 | The snapshot returns 1,000 outstanding lines, including lines beyond the first 25, and returns unavailable without items when a 1,001st line is added. |
| ha-shopping-list-C03 | Protected routes reject missing, revoked, foreign, cross-channel and wrong-purpose credentials. The route is disabled until its digest is set. Calendar, deadline and low-stock scopes stay independent. |
| ha-shopping-list-C04 | The response includes names, quantities, units and opaque item identities. Repeated reads leave the task, inventory, shopping and command records unchanged. |
| ha-shopping-list-C05 | The item identities survive quantity changes. Disposable Core checks the entity and item identities after bearer rotation and process restart, and verifies that isolated sources receive distinct entities and item identities. |
| ha-shopping-list-C06 | Disposable Core distinguishes a valid empty list from unavailability, clears the native item subscription after denial, and recovers after the next valid read. Entity actions reject adding, editing, completing or deleting items. The entity exposes no reorder feature. English and Spanish labels and decimal quantities are checked. |
| ha-shopping-list-C07 | The container acceptance uses the packaged Supervisor and HTTPS standalone launchers, with separate Edge and Stable fixture data. It reads synthetic stock in disposable Core without a published host port. |

The [Edge artifact declaration](../../addon-edge/artifact.json) records the exact
runtime and installed wheel and UI hashes. SQLite schema remains 34.
