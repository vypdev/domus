# Intended household journey

These complete household workflows are still under development. This guide describes the intended
first integrated release. The [current HA preview](installation-home-assistant.md) describes what is available today.

Open Domus with your own Home Assistant account. Ingress uses the existing HA session; standalone offers HA sign-in. The complete release will provide Dashboard, Tasks, Calendar, Shopping,
Inventory, Family or Settings. English and Spanish are supported. Your role controls permitted actions,
with backend checks applying even when a client presents an outdated button.

During explicit setup, choose how administration maps from HA: all HA administrators by default, only the verified administrator completing setup, or an explicitly selected HA user. The default gives each proven HA administrator inherited Domus administration; ordinary users are not promoted by opening the app. An administrator configures household permission profiles and per-member exceptions. Known suspension or revoked authority still blocks access; changing a label or choosing another performer never changes the caller's permission.

## Household navigation

Once household access is verified, **Overview** jumps to your current household status and
**Tasks** opens the task workspace. **Household** opens administration. The same links work in Home Assistant Ingress and
standalone. Use Tab and Enter or the browser's Back and Forward actions. Moving between
sections keeps an unsent draft in the current page; reload verifies access again and does
not restore an unsent administration draft.

## Current task workspace

The current source increment adds a real task workspace. Published Edge.7 remains administration-only until the next verified preview package is adopted; refreshing that older app does not install this source change.

- In **Tasks**, open **New task**, enter a title, optional instructions and priority, then choose **Create task**. The title-only flow creates actual work, not a schedule draft.
- Select a task to inspect it. **Claim task** assigns eligible work to your own verified membership. **Mark done now** records you as the performer at the current server-anchored time.
- Restricted performers require adult approval by default. An authorized adult can approve or reject the current cycle; rejection and reopening require a reason. Reopening preserves the previous cycle and its verification evidence.
- If a task already has linked materials, review its quantities before completion. Decimal input is converted exactly, including a comma separator, and the linked unit's precision is enforced. Zero means unused. Separate-recording tasks do not silently submit planned consumption.
- A lost reply leaves a visible saved request. **Check saved request** reads its original result without sending another change. New changes remain blocked while an earlier request is unconfirmed. Resolved browser records can be dismissed without deleting server history.
- **Household** opens identity, participants, preferences and access settings. Task IDs, revisions and resolved recovery records stay in optional details. A saved language preference applies to both workspaces.

The workspace uses the server's current allowed actions. Read-only HA outage grace permits local queries until the original session deadline and blocks changes. A changed account or membership retires the previous private draft.

The Points and Inventory consumers record their own effects. Check Family for posted points and the task material outcome for posted stock movements or pending regularization. Use Family to review contributions and request optional rewards.

## Daily work

The development task API is documented in [task execution](tasks/execution.md), with
[operation/recovery guidance](tasks/operator-recovery.md) and [migration limits](tasks/migration.md).
The following sections combine current task workflows with the intended release scope.

Create a task with only a title, then optionally set category, priority, duration, assignment, materials,
schedule, recurrence and verification. Claim available work or inspect assignments.
When completing, name the actual performers. A task awaiting verification does not award points yet.
For tasks with materials, review the planned amounts, adjust them to actual usage and submit them with completion. An unused material can explicitly have zero usage. The task can instead be configured for separate recording. Insufficient stock keeps the work completed and the affected consumption pending regularization; the result shows which material lines posted and which need review without inventing negative stock. Reopening or rejecting verification does not automatically return consumed supplies.
Adults need no verification by default; restricted performers require authorized-adult approval unless an administrator has explicitly configured a permitted task override. Recording someone else's work does not change that performer's role.
An adult with approval permission may approve work in which they participated by default. Household
configuration or an administrator-authorized task setting may require an adult who did not perform
that work instead. Restricted members cannot approve their own work.

Restricted members may confirm actual usage of the materials linked to a task they are authorized
to complete, without general inventory access. Household/task policy and explicit member denials
still apply. If the required material authority is absent, valid performed work stays recorded and
the result identifies material usage awaiting authorized follow-up. A later permission grant or
task approval does not silently consume that material.

Completing a recurring occurrence leaves its definition intact. Reopening retains history and reverses
awards with visible ledger entries.
If a prerequisite is reopened after dependent work was completed, that dependent keeps its completion and points. Domus marks the changed dependency for review and links the prerequisite; it does not reopen a chain of work automatically.

Calendar labels scheduled work, deadlines and actual completion separately. Fixed schedules keep their anchor
when completed late; relative schedules count from the actual work-completion date even when approval comes later.
By default the next occurrence appears when work is recorded, while any required approval holds its points. An authorized task setting can wait to show the next occurrence until approval, preserving the same due date.
When a daylight-saving change makes a scheduled time nonexistent, Domus keeps that occurrence and moves it forward to the first valid local time. The calendar shows the intended time and its adjustment; a 02:30 task in a 02:00–03:00 gap appears at 03:00.
When autumn repeats a local time, the task executes once at the first appearance by default. A household setting may select the second appearance; preview shows the resolved offset and preserves existing work.
Use month/week/day/agenda and member/category/status/priority/type filters.
Missed occurrences remain visibly pending by default. A per-task policy can change how missed work is handled; explicitly skipping work retains a skipped record and awards no completion points.
Changing recurrence shows a preview of future changes. Only executions that have not started are updated; work underway and history remain. If someone starts a task after the preview, refresh the plan before applying it. Explicit exceptions and any overlaps remain visible for review.

## Supplies and shopping

### Inventory catalog and Pantry intake

Open **Inventory** to browse your household's registered products. Pantry shows
the recorded stock, the part reserved for work and the amount available after
reservations. Use **Show more products** when the current page is full.

If your household grants inventory management, enter a product name and select
pieces, grams or millilitres under **Register product**. The base unit stays fixed.
For opening stock or later additions, choose **Record stock intake** on the
product, enter the amount in its base unit and review the amount before choosing
**Confirm intake**. Pieces require a whole number. Grams and millilitres allow
up to six decimal places, using a decimal point or comma.

The result shows the amount recorded and its receipt details. If the result is
unconfirmed, choose **Recover original request** in the same tab. The original
key prevents a second stock entry, including after reload. A historical receipt
can be viewed after restoring a backup. Check the current recorded stock before
making another request.

### Movement history and corrections

Choose **Show movement history** on a product. Each entry shows its signed
quantity, unit, source, author and date in UTC. **Show older movements**
continues the current view. **Refresh inventory** shows newer entries. Movement
details identify the original and compensating entries when a correction is linked.

If you have inventory management access, choose **Adjust stock** in the history.
Enter a positive or negative quantity and explain the physical count or other
change. To undo an erroneous intake, use **Reverse this intake** on the original
entry and confirm the full removal with a reason. When the original quantity was
wrong, record the replacement quantity through normal intake after reversal.
Both actions use the product's existing unit and precision. Stock needed by
active reservations stays reserved. Review task usage and pending
regularization in **Tasks**.

If a reply is lost, choose **Recover original request** in the same tab, even
after reloading. A historical receipt can refer to a movement that was recorded
after the restored backup. Check the current history and balance before
submitting a new request.

### Pantry replenishment

Each Pantry product shows its minimum, target and current amount to replenish
in the base unit. Available stock is recorded stock minus active reservations.
When available stock falls below the minimum, Pantry shows the amount needed
to reach the target. At the minimum or above it shows that replenishment is
satisfied. Refresh Inventory after stock or reservations change.

With inventory management access, choose **Edit replenishment** on the product.
Enter a nonnegative minimum and a target at least as large. Pieces use whole
numbers. Grams and millilitres allow up to six decimal places. Use a minimum of
zero to turn replenishment off. If another edit wins first, review the current
values and reopen the editor. If the reply is lost, choose **Recover original
request**.

### Shopping and physical receipts

In **Inventory**, choose **Show purchases** in the Shopping card. With shopping
management access, select a Pantry product or enter an untracked item and record
the quantity bought. Tracked purchases use the product's base unit. Untracked
items use whole pieces. A product can have one open purchase while some units
are still due or awaiting Pantry posting. The amount still to buy for Pantry
accounts for those incoming units.

Choose **Show physical receipts** on a purchase. Record the amount that arrived,
up to the amount still due. The purchase keeps its original quantity and shows
how much arrived and how much is still due. An untracked arrival is complete at
this point. For a tracked item, an inventory manager chooses **Post to Pantry**
on each physical receipt. The receipt then shows the linked stock movement.

If Pantry cannot accept the full receipt, make space and post that saved receipt
again. If a response is lost, choose **Recover original request**. After a
snapshot restoration, check the current receipt and stock before making a new
request.

### Subsequent supplies workflows

Add products independently from package formats and locations. Receive physical quantities into their base unit.
Record consumption explicitly. Shopping will combine attributable needs from Pantry replenishment and task materials.
Scan a barcode with the camera or enter it manually. Domus searches local products first. If an administrator configures Internet product lookup, you may retrieve a candidate and review its source before importing it. External unavailability does not block local search or manual creation.
Manual additional requests remain additional unless you choose overlapping intent.

## Participation

Open Family to see your balance, point history and recorded work. Select a week or
month using a date in that period. The household time zone determines where the
work belongs. Sunday work stays in Sunday's week if it is approved on Monday.
The report separates estimated points awaiting verification and points awaiting
posting. Points become available when posted.

History shows the work, approval and posting times separately. A reversal stays
linked to its original award and corrects the earned points in the work period.
Family shows elapsed time for completions with a recorded start and identifies
how many completions contributed to that estimate.

Administrators can change the household default under **Family → Points allocation**
or set a **Task override** on a task. **Use household default** clears the override
for future completions. Choose a conserved split, equal shares with an explicit
rounding rule, full points for every participant, or administrator-entered manual
shares. Choose whole points or two decimal places.

Open **Preview points** in the task completion form. Select the participants who
performed the work and check the base points, individual amounts, and actual total
before recording it. The form asks for a new preview when the participants or
amounts change. Family history retains the applied policy, its revision, and the
actual amounts when you change settings or reopen a task.
Rewards are optional and do not control access to normal household responsibilities.
### Rewards

In **Family → Rewards**, check the catalog and the available balance. Select an
eligible reward and review its cost and remaining available points before
confirming. The request reserves its original cost. Posted points, active
reservations, and available points are shown separately.

Share the request code with a points administrator for review and delivery.
Administrators can enable rewards, manage catalog eligibility and prices, and use
a shared code to approve a request or record physical delivery. The request
history stays in the requesting member's workspace. Cancelling an open request
requires a reason and releases its reservation.

An approved reward may enter funding hold after a reversal. Family shows the
remaining shortfall, retained approval, and reservation. New earned points can
restore backing. The administrator records physical delivery as a separate action.
Delivery records one spending entry and releases the reservation. Spending is
shown in its posting period, while earned points belong to the work period.

A reversal can leave a negative posted balance after delivery. The delivered
reward remains recorded, and later earned points cover the deficit.

## Clear state and recovery

Loading does not mean zero records. A saved task with a pending HA update is still saved.
A conflict keeps your entered values; review the latest record before resubmitting.
If the server is unavailable, your unsaved screen draft is not falsely labeled as committed or queued for offline sync.
Use the operation/history link to inspect what succeeded and what remains.

## Household automation

Settings -> Automations offers a simple/default editor and optional advanced editor in the first release. Start from a typed trigger, conditions and actions; advanced mode adds branches, bounded repetition/parallel steps and durable waits. Both views save the same rule. If the simple form cannot represent advanced content, it shows a summary and opens the advanced editor rather than deleting fields.

Preview explains why a condition matches and what would happen without performing the actions. Enabling a validated rule is explicit. Execution history shows each saved effect, pending wait and safe retry/cancel action. If a task was created but a later notification failed, the task remains created and the retry addresses the notification. External HA automations may call the same public Domus actions.
Disabling stops new executions and subsequent steps in queued, waiting or active runs. A step already executing atomically may finish and its result remains in history. The status identifies any outcomes still settling. Re-enabling allows future triggers without silently resuming those cancelled runs or undoing saved effects.

## Channels and privacy

Stable is production; Edge is experimental and has separate data, credentials and HA identities.
No AI or external catalog is required. External calendar/export functions remain off unless explicitly configured.
