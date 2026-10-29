# Intended household journey

Domus is not implemented yet. This guide describes the first integrated release.

Open Domus, sign in with your own Home Assistant account and use Dashboard, Tasks, Calendar, Shopping,
Inventory, Family or Settings. English and Spanish are supported. Your role controls permitted actions,
with backend checks applying even when a client presents an outdated button.

## Daily work

Create a task with only a title, then optionally set category, priority, duration, assignment, materials,
schedule, recurrence and verification. Claim available work or inspect assignments.
When completing, name the actual performers. A task awaiting verification does not award points yet.
For tasks with materials, review the planned amounts, adjust them to actual usage and submit them with completion. An unused material can explicitly have zero usage. The task can instead be configured for separate recording. Insufficient stock keeps the work completed and the affected consumption pending regularization; the result shows which material lines posted and which need review without inventing negative stock. Reopening or rejecting verification does not automatically return consumed supplies.
Adults need no verification by default; restricted performers require authorized-adult approval unless an administrator has explicitly configured a permitted task override. Recording someone else's work does not change that performer's role.
Completing a recurring occurrence leaves its definition intact. Reopening retains history and reverses
awards with visible ledger entries.

Calendar labels scheduled work, deadlines and actual completion separately. Fixed schedules keep their anchor
when completed late; relative schedules count from the actual work-completion date even when approval comes later.
By default the next occurrence appears when work is recorded, while any required approval holds its points. An authorized task setting can wait to show the next occurrence until approval, preserving the same due date.
When a daylight-saving change makes a scheduled time nonexistent, Domus keeps that occurrence and moves it forward to the first valid local time. The calendar shows the intended time and its adjustment; a 02:30 task in a 02:00–03:00 gap appears at 03:00.
Use month/week/day/agenda and member/category/status/priority/type filters.
Missed occurrences remain visibly pending by default. A per-task policy can change how missed work is handled; explicitly skipping work retains a skipped record and awards no completion points.
Changing recurrence shows a preview of future changes. Only executions that have not started are updated; work underway and history remain. If someone starts a task after the preview, refresh the plan before applying it. Explicit exceptions and any overlaps remain visible for review.

## Supplies and shopping

Add products independently from package formats and locations. Receive physical quantities into their base unit.
Record consumption explicitly. A low-stock policy or missing task material creates an attributable shopping demand.
Scan a barcode with the camera or enter it manually. Domus searches local products first. If an administrator configures Internet product lookup, you may retrieve a candidate and review its source before importing it. External unavailability does not block local search or manual creation.
Manual additional requests remain additional unless you choose overlapping intent.
A purchase can be partially received. Inventory is updated only for confirmed receipts, once.
Free-text groceries need no tracked product.

## Participation

Family shows assignments, completed work, estimated effort and point history.
Work performed on Sunday belongs to Sunday's household week even if approved Monday. While approval is pending, its points are not spendable; approval updates the original week's earned total and credits the current balance. History shows work, approval and posting times separately. Weekly earned points are distinct from your remaining balance after rewards.
An administrator configures collaborative allocation in the application. The default divides one conserved total, but the household may choose equal shares rounded down or up, two-decimal shares, full points for every performer, or authorized manual amounts. For a 10-point task with three performers, the selected policy can produce 3/3/4, 3/3/3, 4/4/4, 3.33/3.33/3.33 or 10/10/10. The preview and ledger explain the base value, policy, each share and actual total. Changing policy does not rewrite past awards; corrections and reopening compensate the amounts actually awarded.
Rewards are optional and do not control access to normal household responsibilities.
If reopening reverses points already spent, the balance can become negative. The history explains the deficit, earned points offset it, and new redemptions remain unavailable until the balance recovers and covers the reward cost. Delivered rewards remain delivered.

## Clear state and recovery

Loading does not mean zero records. A saved task with a pending HA update is still saved.
A conflict keeps your entered values; review the latest record before resubmitting.
If the server is unavailable, your unsaved screen draft is not falsely labeled as committed or queued for offline sync.
Use the operation/history link to inspect what succeeded and what remains.

## Household automation

Settings -> Automations offers a simple/default editor and optional advanced editor in the first release. Start from a typed trigger, conditions and actions; advanced mode adds branches, bounded repetition/parallel steps and durable waits. Both views save the same rule. If the simple form cannot represent advanced content, it shows a summary and opens the advanced editor rather than deleting fields.

Preview explains why a condition matches and what would happen without performing the actions. Enabling a validated rule is explicit. Execution history shows each saved effect, pending wait and safe retry/cancel action. If a task was created but a later notification failed, the task remains created and the retry addresses the notification. External HA automations may call the same public Domus actions.

## Channels and privacy

Stable is production; Edge is experimental and has separate data, credentials and HA identities.
No AI or external catalog is required. External calendar/export functions remain off unless explicitly configured.
