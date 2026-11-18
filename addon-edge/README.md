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

This candidate uses SQLite schema 33. Keep a
compatible image and cold data backup before upgrading a previous preview.
See [installation and operation](DOCS.md) for the source pin and rollback
instructions.
