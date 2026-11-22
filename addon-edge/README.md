# Domus Edge

Development preview of Domus installed as a Home Assistant app. Open it through
HA's Open Web UI using your existing Home Assistant session.

Edge.75 rejects unsupported control characters in a shopping note while preserving
the accepted text for correction and retry.

Edge.74 keeps the note and priority labels aligned with the household interface's
typography, including when a named font is unavailable.

Edge.73 lets each manual shopping request keep an optional plain-text note and
a Low, Normal, High or Urgent priority. Notes accept up to 1,000 Unicode
characters, including multiple lines. Source details retain each request's own
note, priority and quantity. Correcting an error keeps the entered fields;
recovering an earlier request preserves a later unrelated draft.

Edge.72 enables saved daily task automations after reviewing the exact revision,
conditions and timing. The narrow permission belongs to the household rule and
continues without an open browser or its activating member. Daily history shows
actual tasks, unmet conditions and cancelled work. Recover interrupted controls
by checking the original daily request. Household timing changes retain the approved
schedule until explicit adoption; times missed while stopped are skipped, while
already admitted work is preserved. Disable future work without removing prior tasks.

Edge.70 lets Tasks plan existing Pantry materials for ordinary, fixed and relative
creation, review per-line usage and explicitly settle pending consumption. Reopening
retains each completion's earlier usage. **More products** keeps earlier catalog choices available
so a plan can combine products across pages. **Next closed completion** remains available
after settlement or original-request recovery, without changing the reopened task.
A saved creation clears its submitted material plan even if reading the result fails.
Use the focused **Refresh tasks** control to recover; checking an already saved creation
preserves a later unrelated plan. The recovery control stays visible below fixed
navigation, including when a long creation draft remains open. Opening, refreshing
or paging material choices preserves the earlier usage and next completion being reviewed.
A temporary history-read failure keeps the selected task and its continuation available for retry.
A later keyboard action keeps focus when a material control has a pending focus continuation.
Focused material choices and outcomes stay visible below fixed navigation.
Settling the current completion also preserves the earlier usage page and its next completion.

A denied material catalog explains how to recover even when the plan is empty.
Clearing a retained denied plan returns focus to the task title and preserves its text.
A temporary initial task-detail or closed-cycle read failure before settlement retains the earlier usage and next page;
no consumption is submitted until you explicitly retry.

Edge.32 shows the outstanding shopping count and the first 25 rows in Overview.
Select a row to open the matching item in the shared list in Inventory.

In Household settings, preview a manual task proposal and optionally check available
stock against a product's minimum. Edge.33 saves that rule as an inactive draft,
retains immutable revisions and lets you check the original save after a lost response.

Edge.38 enables an exact saved revision for an explicit manual run. Check the
original outcome after an interruption and open the created task from its receipt.

Edge.47 completes requested stops through explicit runtime cleanup. Restarting the
app retains its installation identity and original household operations.

Edge.48 lets task managers assign active household members, replace the selected
people and release eligible work from Tasks. A competing update retains the draft
for explicit review. Saved requests recover an interrupted assignment response.

Edge.49 enables assignment saving after the selected members change and explains
when the current selection already matches the task.

Edge.50 adds Start, Block and Unblock to Tasks, with a required blocking reason,
explicit conflict review and recovery of the original progress request.
Edge.51 refreshes both the list and detail after a competing progress update and
keeps the mobile task layout within the available width.

Edge.52 finds household products from manually entered barcode digits. Inventory
managers review a local product association or its removal before confirming.
Original-request recovery and current conflict review retain the entered code.

Edge.53 continues keyboard focus to the barcode result or retry control after a
submitted search.

Edge.54 continues keyboard focus after confirmed barcode changes and moves it to
original-request recovery when a write response is unconfirmed.

Edge.55 aligns barcode HTTP validation and published API schemas with the same
supported printed lengths.

Edge.56 retires loaded Inventory data when current access is rejected and focuses
Refresh inventory. An authorized refresh preserves the entered barcode digits.

Edge.57 hides all household information when the current session is rejected and
focuses **Reopen Domus**. Existing records and original requests are retained.
After verifying access, recover an interrupted request explicitly; reopening the
interface never repeats it automatically. Granular permission denials still offer
the corresponding workspace's current recovery action.

This candidate uses SQLite schema 37. Keep a
compatible image and cold data backup before upgrading a previous preview.
See [installation and operation](https://github.com/vypdev/domus/blob/develop/addon-edge/DOCS.md) for the source pin and rollback
instructions.
