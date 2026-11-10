# Family M2 qualification

Family is the last M2 increment before supplies work. Its contract and retained
case inventory are in the [Points and rewards specification](../../specs/points-rewards.md).

| Increment | Verification |
| --- | --- |
| Protected balance, history, and participation | [PR #63](https://github.com/vypdev/domus/pull/63), [exact-head CI](https://github.com/vypdev/domus/actions/runs/42705292838), and [Bugbot](https://github.com/vypdev/domus/pull/63#issuecomment-6752372553) on `29844af`. |
| Configurable allocation and frozen award evidence | [PR #66](https://github.com/vypdev/domus/pull/66), [exact-head CI](https://github.com/vypdev/domus/actions/runs/42718494625), and [Bugbot](https://github.com/vypdev/domus/pull/66#issuecomment-6753834278) on `212296c`. |
| Reward reservations, approval, delivery, cancellation, and funding holds | [Issue #65](https://github.com/vypdev/domus/issues/65). The linked PR records the exact-head CI and Bugbot evidence. |

The protected Family report separates posted balance, active reservations, and
available points. Pending verification and pending posting remain separate.
Earned points and reversals follow the original work period in the household
zone. Reward spending follows its posting period. Each detailed list identifies
its bounded window, while period totals cover the full selected period.

The optional reward catalog starts disabled. A request reserves the catalog
price seen at its current revision and keeps that price if the offer changes.
Only an administrator with current points-management authority can approve or
record delivery. The member shares a request code with the administrator.
Management commands return the transition state and revision. The requesting
member's private history and balances remain member-scoped.

A reversal and a reward command use the same SQLite writer. If backing is lost,
a hold keeps approval and the reservation. Restored backing permits an explicit
delivery. Delivery posts one spend and releases the reservation in that
transaction. Cancellation releases an open reservation and records its reason.
A delivered reward remains recorded through a negative posted balance.

## Evidence by case

| Case | Executable evidence |
| --- | --- |
| `family-participation-C01`–`C04` | [Family HTTP tests](../../tests/backend/test_family_http.py) and [Points consumer tests](../../tests/backend/test_points_consumer.py) cover member scope, work periods, corrections, restart, and activated restoration. |
| `family-participation-C05` | The [compiled workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) covers Ingress and standalone, English and Spanish, and the signed history. |
| `family-allocation-C01`–`C05` | The [allocation evidence](../tasks/points-consumer.md#configured-allocation) maps exact splits, authorized revisions, frozen pending work, concurrency, recovery, and localized preview and history. |
| `family-redemption-C01` | [Reward HTTP tests](../../tests/backend/test_rewards_http.py) cover both protected compositions, scoped reads and cursors, current authority, and rejected attempts without effects. |
| `family-redemption-C02` | [Reward storage tests](../../tests/backend/test_rewards_storage.py) race two funded requests. The HTTP lifecycle changes the catalog price after reservation and retains the original cost. |
| `family-redemption-C03` | The HTTP lifecycle verifies a single spend on delivery replay and one release on cancellation. Storage tests inspect the retained approval and funding effects. |
| `family-redemption-C04` | The storage tests race the Points reversal with admission and delivery. The HTTP lifecycle verifies a hold, blocked delivery, and retained spending after a negative balance. |
| `family-redemption-C05` | The storage tests activate a real checkpoint with an existing hold and recover a later delivery as historical. Migration uses the [schema 18 fixture](../../tests/fixtures/sqlite/v18-rewards-source.sql), and corruption tests reject unsafe checkpoints. |
| `family-redemption-C06` | The [Chromium workspace journey](../../frontend/tests/e2e/workspace-navigation.spec.ts) exercises the full reward lifecycle in both deployments and locales. [Frontend tests](../../frontend/tests/rewards.test.ts) exercise original-result recovery, exact revisions, and accessible presentation states. |

## Merge evidence

Run the application, architecture, and documentation checks. Backend lines and
branches and frontend lines, branches, statements, and functions must all be
100% globally and per authored file. Run the compiled Chromium journeys in
Ingress and standalone. The repository CI builds and tests the amd64 and ARM64
images, exercises both deployments with the installed browser assets, and
checks migration and restore compatibility. Record the exact-head CI and
Bugbot conclusions in the linked PR before merge.
