# Domus Edge

Development preview of Domus installed as a Home Assistant app. Open it through
HA's Open Web UI using your existing Home Assistant session.

Edge.32 shows the outstanding shopping count and the first 25 rows in Overview.
Select a row to open the matching item in the shared list in Inventory.

In Household settings, preview a manual task proposal and optionally check available
stock against a product's minimum. Edge.31 keeps the preview available when the
product list fails to load and preserves the draft while retrying the list.

This candidate uses SQLite schema 31. Keep a
compatible image and cold data backup before upgrading a previous preview.
See [installation and operation](DOCS.md) for the source pin and rollback
instructions.
