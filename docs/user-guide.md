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

### Task summary on Overview

**Overdue** shows open tasks past their deadline. **Due today** shows open tasks
due on the current local day whose deadlines are still ahead or due now.
Timed deadlines use the household time zone. Date-only recurring deadlines
use their saved scheduling time zone and stay due through that day.
**Upcoming maintenance** shows open scheduled tasks from tomorrow through
the seventh upcoming local day, in date order.
**Assigned to me** shows your assigned, in-progress, and blocked tasks.
**Unclaimed tasks** shows household work in the available state.

Each group shows an exact total and up to 25 items. Select a task to open
its current details in Tasks. Use **Retry task summary** if the summary
could not be loaded. Access follows your current Tasks read permission.

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

### Storage locations and transfers

Choose **Show movement history** to see the product's recorded, reserved and
available stock at each location and across the household. Pantry remains the
location used by ordinary intake, adjustments, Shopping receipts and Pantry
replenishment.

With inventory management access, enter a name under **Storage locations** and
choose **Add location**. On the product, choose **Move stock**, select the origin
and destination, and enter the amount in its base unit. The form shows how much
stock is available at the origin after reservations. Choose **Review transfer**
and check the locations and amount before choosing **Confirm transfer**.

The two linked entries show where the stock moved, the amount and who recorded
it. If the quantity exceeds the available stock, revise it and try again. If
the result is unconfirmed, choose **Recover original request** before sending
another transfer. Check current balances when a restored request is historical.

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

### Shared shopping list

In **Inventory**, choose **Show shared shopping list** in the Shopping card.
Each Pantry product shows the amount to buy and the contribution from Pantry,
Tasks and manual extras. Choose **Show shopping sources** to see the Task
material plans, matched reservations, available stock and incoming purchases
that affect the total. Task information appears for members who can read Tasks.

With shopping request access, add a Pantry product in its base unit or enter a
name and a whole number of pieces. Free-text requests stay separate even when
their names match a Pantry product. A shopping manager can clear an untracked
extra from the list or a tracked extra from its source details. Changes to
stock, reservations and purchases recalculate automatic needs. Extras stay on
the list until a manager clears them. Use **Recover original request** if an
add or clear response is lost.

### Purchase sessions

In the shared shopping list, a shopping manager can choose **Add to purchase
session** on two to sixteen different items. Review the quantities you actually
bought, enter a name in **Store (optional)** if known, and choose
**Record purchase session**. Tracked quantities use each
product's base unit. Untracked extras use whole pieces. If any selected
tracked product already has an open purchase, review that purchase and adjust
the selection before saving the session again.

Choose **Show purchase sessions** to browse trips by shopper and time, with the
store shown when provided. Open a session to see the store and the amounts
purchased, received, still due and awaiting Pantry
posting for each item. Use **Show physical receipts** on an item to record an
arrival, cancel the outstanding balance, or post a receipt to Pantry with the
required access. Manage manual extras
using their existing clear controls.

If the session response is lost, choose **Recover original request** and then
**Show recorded session** to open the saved trip.

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

### Voiding a physical receipt

With shopping management access, open **Show physical receipts** on a tracked
purchase with its balance still active. On the mistaken receipt, choose
**Void receipt**, review the quantity, enter a reason and confirm.

The original receipt stays in history with the reason, shopper and time of
the void. Its quantity returns to **Still due**. Use **Record physical
receipt** to enter the amount that actually arrived. An inventory manager can
then post the new receipt to Pantry. If the void response is lost, choose
**Recover original request**.

### Correcting a receipt already posted to Pantry

With both shopping and inventory management access, open **Show physical
receipts** on a tracked purchase with its balance still active. Choose
**Correct posted receipt**, review the full quantity, enter a reason and
confirm. The correction records a linked negative Pantry movement and
returns the same quantity to **Still due**. You can then record and post the
actual arrival.

The receipt history shows both movement identifiers, the reason, author and
time. Inventory shows the original entry and its compensating movement.
Review active reservations and any other open purchase for the product if a
correction is rejected. If the response is lost, choose **Recover original
request**.

A previous reversal made directly in Inventory is labeled separately in
receipt history. Its original operation remains available for recovery.

### Recording a physical return

With both shopping and inventory management access, open **Show physical
receipts** for a fully received and posted purchase item. On the receipt,
choose **Record physical return**, review the full quantity, enter a reason
and confirm.

Shopping keeps the original purchased and received amounts and shows the
return reason, author and time. Pantry records the exact withdrawal with a
link to the original intake. The shared list uses the resulting stock when
calculating replenishment.

Review active reservations if a return is rejected. A receipt already
corrected or returned has its history available for review. Choose **Recover
original request** when a return response is lost.

### Cancelling an outstanding purchase balance

With shopping management access, open **Show physical receipts** for the
purchase item. Choose **Cancel outstanding balance**, review the exact quantity
to cancel, enter a reason, and choose **Confirm cancellation**.

The item keeps its purchased quantity and receipt history. Its details show
the cancelled quantity, reason, shopper and time. Inventory managers can still
post any physical receipts that were already recorded. Cancelling the balance
removes that quantity from incoming supply so unmet Pantry and Task demand
can return to the shared list. If the response is lost, choose **Recover
original request**.

### Subsequent supplies workflows

Add products independently from package formats and locations. Receive physical quantities into their base unit.
Record consumption explicitly in Tasks.
Scan a barcode with the camera or enter it manually. Domus searches local products first. If an administrator configures Internet product lookup, you may retrieve a candidate and review its source before importing it. External unavailability does not block local search or manual creation.

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
