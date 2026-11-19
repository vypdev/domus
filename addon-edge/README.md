# Domus Edge

Development preview of Domus installed as a Home Assistant app. Open it through
HA's Open Web UI using your existing Home Assistant session.

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

This candidate uses SQLite schema 35. Keep a
compatible image and cold data backup before upgrading a previous preview.
See [installation and operation](https://github.com/vypdev/domus/blob/develop/addon-edge/DOCS.md) for the source pin and rollback
instructions.
