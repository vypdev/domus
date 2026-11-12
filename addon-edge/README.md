# Domus Edge

Development preview of Domus installed as a Home Assistant app. Open it through
HA's Open Web UI using your existing Home Assistant session.

In Household settings, preview a manual task proposal and optionally check available
stock against a product's minimum. Edge.30 keeps the preview available when the
product list fails to load and preserves the draft while retrying the list.

This candidate uses SQLite schema 31. Keep a
compatible image and cold data backup before upgrading a previous preview.
See [installation and operation](DOCS.md) for the source pin and rollback
instructions.
