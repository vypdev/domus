# Intended household journey

Domus is not implemented yet. This guide describes the first integrated release.

Open Domus, sign in with your own Home Assistant account and use Dashboard, Tasks, Calendar, Shopping,
Inventory, Family or Settings. English and Spanish are supported. Your role controls permitted actions,
with backend checks applying even when a client presents an outdated button.

## Daily work

Create a task with only a title, then optionally set category, priority, duration, assignment, materials,
schedule, recurrence and verification. Claim available work or inspect assignments.
When completing, name the actual performers. A task awaiting verification does not award points yet.
Completing a recurring occurrence leaves its definition intact. Reopening retains history and reverses
awards with visible ledger entries.

Calendar labels scheduled work, deadlines and actual completion separately. Fixed schedules keep their anchor
when completed late; relative schedules start from accepted completion according to their preview.
Use month/week/day/agenda and member/category/status/priority/type filters.

## Supplies and shopping

Add products independently from package formats and locations. Receive physical quantities into their base unit.
Record consumption explicitly. A low-stock policy or missing task material creates an attributable shopping demand.
Manual additional requests remain additional unless you choose overlapping intent.
A purchase can be partially received. Inventory is updated only for confirmed receipts, once.
Free-text groceries need no tracked product.

## Participation

Family shows assignments, completed work, estimated effort and point history.
Collaborative awards disclose the total and each share. Corrections preserve the original record.
Rewards are optional and do not control access to normal household responsibilities.

## Clear state and recovery

Loading does not mean zero records. A saved task with a pending HA update is still saved.
A conflict keeps your entered values; review the latest record before resubmitting.
If the server is unavailable, your unsaved screen draft is not falsely labeled as committed or queued for offline sync.
Use the operation/history link to inspect what succeeded and what remains.

## Channels and privacy

Stable is production; Edge is experimental and has separate data, credentials and HA identities.
No AI or external catalog is required. External calendar/export functions remain off unless explicitly configured.
