# Changelog

## 0.0.0-edge.67

- Keep current material settlement available when the task itself cannot accept another revision.
- Leave revision-dependent task actions disabled at their existing limit.

## 0.0.0-edge.66

- Preserve the displayed earlier material usage and its next page when settling the current completion.
- Keep that history continuation when recovering the original settlement after a lost reply.

## 0.0.0-edge.65

- Keep focused material choices and outcomes visible below fixed navigation.

## 0.0.0-edge.64

- Respect a newer keyboard target when a material control has a pending focus continuation.
- Retain the selected task, earlier usage and next page after a transient history-read failure.

## 0.0.0-edge.63

- Keep displayed earlier material usage when opening, refreshing or paging material choices.
- Preserve the next closed completion while preparing an unrelated task plan.

## 0.0.0-edge.62

- Keep the focused read-recovery control visible below fixed navigation inside Home Assistant.
- Preserve an unrelated open material draft while checking an already saved creation.

## 0.0.0-edge.61

- Clear the submitted material plan when creation is committed, even if reading the result fails.
- Preserve a later unrelated plan when checking an already saved creation.
- Focus Refresh tasks after a failed post-create read and retain focus while editing the next draft.

## 0.0.0-edge.60

- Keep the next closed completion reachable after settling earlier material usage.
- Preserve this continuation when recovering the original settlement after an interrupted reply.
- Retain the original cycle and intent identities without changing the reopened task.

## 0.0.0-edge.59

- Keep earlier material usage visible and explicitly recoverable after reopening a task.
- Clear the submitted material plan after recovering a committed task creation.
- Keep quantity edits focused without reloading household proof on each keystroke.
- Show exact planned completion decimals with the Spanish separator.
- Include optional Pantry plans, per-line outcomes and published ha-ui next.4 from the unaccepted Edge.58 preview.

## 0.0.0-edge.58

- Plan Pantry materials during ordinary, fixed and relative task creation.
- Show per-line actual consumption and explicitly settle pending usage or record a missing quantity.
- Retain drafts and exact original requests across failures, conflicts and recovery.
- Use published ha-ui next.4 so long mobile product menus preserve their scroll position.

## 0.0.0-edge.57

- Remove shared household/workspace facts when a protected response rejects the current session.
- Focus access verification and retain original requests for deliberate recovery without duplicate writes.
- Fence cancelled or retired responses from newly verified sessions.

## 0.0.0-edge.56

- Retire loaded Inventory data and management controls when current access is rejected.
- Continue a rejected barcode search to Refresh inventory, preserving the input for an authorized retry.

## 0.0.0-edge.55

- Align barcode HTTP validation and published API schemas with the supported printed GTIN lengths.

## 0.0.0-edge.54

- Continue keyboard focus to the current barcode result after confirmed changes and stale-removal review.
- Focus original-request recovery when an association write has an unconfirmed response.

## 0.0.0-edge.53

- Continue keyboard focus to the barcode result or retry control after a submitted search.
- Preserve focus that has moved to another control while the lookup is running.

## 0.0.0-edge.52

- Find a local household product from its printed GTIN barcode digits.
- Review a product association or removal before confirming, with current conflict recovery.
- Retain entered digits through failed reads and recover original writes after interruption.
- Migrate inventory from supported earlier schemas to schema 35. Keep the previous compatible image and cold data checkpoint for rollback.

## 0.0.0-edge.51

- Refresh the task list and selected detail together after a competing progress update.
- Preserve the proposed blocking reason while reviewing current facts.
- Keep the mobile task layout within the available width across system fonts.

## 0.0.0-edge.50

- Start, block and unblock eligible work from Tasks with an explicit confirmation.
- Preserve blocking reasons through conflicts and interrupted responses, with original-request recovery.
- Keep task primary actions readable in light and dark themes.

## 0.0.0-edge.49

- Enable assignment saving after the selected household members change.
- Explain unchanged selections and retain the guard when the same members are selected in a different order.

## 0.0.0-edge.48

- Assign, replace and release planned task assignees through the Tasks workspace.
- Retain selected household members while reviewing a competing update or correcting unavailable choices.
- Recover the original recorded assignment after an interrupted response.

## 0.0.0-edge.47

- Complete explicit runtime cleanup when SIGTERM requests a stop.
- Finish worker shutdown, identity disposal and installation-lease release before exiting successfully.

## 0.0.0-edge.46

- Keep the points-allocation cards readable in dark mode when managing tasks and household defaults.

## 0.0.0-edge.45

- Show every open household task occurrence and its current state in a native read-only Home Assistant list.
- Connect the task list with its own optional installation grant.

## 0.0.0-edge.44

- Show the complete outstanding shared shopping list as a native read-only Home Assistant entity.
- Connect it with its own optional installation grant.

## 0.0.0-edge.43

- Share the complete Overview low-stock product count with the native Home Assistant sensor.
- Use an independent read-only grant for each installation and channel.

## 0.0.0-edge.42

- Save and reopen inactive daily drafts with the exact local time and original receipt.
- Migrate SQLite to schema 34 and preserve the original enabled manual revision.

## 0.0.0-edge.41

- Preview five upcoming daily times with the household time zone and daylight-saving policy.

## 0.0.0-edge.40

- Clear open manual run history when Domus observes a change to the member's current access.

## 0.0.0-edge.39

- Review your previous manual automation runs from the saved rule, including the original task outcome and retained results from before restoration.

## 0.0.0-edge.38

- Enable a saved manual automation revision, run it with an original receipt, and disable future runs.
- Migrate SQLite to schema 33 while preserving saved draft revisions and receipts.

## 0.0.0-edge.37

- Retry a draft conflict review without losing the local edit or saving over a stale revision.

## 0.0.0-edge.36

- Keep the draft editor locked while opening a saved rule or checking for an interrupted save.

## 0.0.0-edge.35

- Show the latest saved condition when reviewing a conflicting draft revision.

## 0.0.0-edge.34

- Match the automation draft API contract to the exact supported revision range.

## 0.0.0-edge.33

- Save and reopen inactive manual automation drafts in Household settings.
- Preserve immutable revisions and recover a save after a lost response.
- Migrate existing data to SQLite schema 32. Keep the compatible backup for rollback.

## 0.0.0-edge.32

- Show the exact number of items still to buy and the first 25 shared-list items on Overview.
- Open the selected item in Inventory with keyboard or touch in English and Spanish.

## 0.0.0-edge.31

- Hide the stock condition selector when the catalog is unavailable and has no choices.

## 0.0.0-edge.30

- Keep manual previews available without a stock condition when the product list fails to load.
- Keep the draft while retrying the product list.

## 0.0.0-edge.29

- Preview a manual task proposal in Household settings in English and Spanish.
- Check an optional product condition against current available stock without creating a task.
- Keep the draft after a recoverable error or a return from another workspace.

## 0.0.0-edge.28

- Refresh the Family summary when the household week changes while Overview is open.

## 0.0.0-edge.27

- Show completed tasks and posted earned points for the current Family week on Overview.
- Open Family from the localized summary to review the full report and pending values.

## 0.0.0-edge.26

- Let people with task configuration permission set optional base points when creating a task.
- Keep the household default for title-only creation and accept localized decimal input.
- Explain how to correct a fractional amount when the current allocation requires whole base points.

## 0.0.0-edge.22

- Show completed tasks and posted earned points for the current Family week on Overview in English and Spanish.
- Open Family from the summary to review pending work and the full report.

## 0.0.0-edge.21

- Use singular units when reviewing an intake of exactly one item in English and Spanish.

## 0.0.0-edge.20

- Show products whose available stock falls below their replenishment minimum on Overview in English and Spanish.
- Keep the exact count and open Inventory to review stock and its available actions.

## 0.0.0-edge.19

- Show open scheduled maintenance for the next seven days on Overview in English and Spanish.
- Keep the effective deadline and open the existing Tasks detail from each item.

## 0.0.0-edge.18

- Reload the preview product list on return to Household settings and keep the draft.
- Let members retry an unavailable product list.

## 0.0.0-edge.17

- Preview a manual task proposal in Household settings in English and Spanish.
- Explain whether an optional stock condition matches using current available stock.

## 0.0.0-edge.16

- Show the effective date-only deadline in the task list and selected task detail.

## 0.0.0-edge.15

- Show exact counts of tasks due today and overdue on Overview in English and Spanish.
- Keep the effective deadline of each timed or date-only task and open its existing protected detail.

## 0.0.0-edge.14

- Use singular units for quantities of exactly one in the shared shopping list and purchase history in English and Spanish.

## 0.0.0-edge.13

- Record an optional store on a purchase session and show it in protected trip history.
- Migrate to schema 31 while preserving the original receipts for existing sessions.

## 0.0.0-edge.12

- Show assigned and unclaimed task summaries on Overview with exact authorized totals.
- Open a selected task through the existing protected Tasks detail in English and Spanish.

## 0.0.0-edge.11

- Use singular English and Spanish stock units when the displayed quantity is exactly one.
- Keep schema 30 and the location and transfer history from Edge.10.

## 0.0.0-edge.10

- Qualify storage locations, exact stock transfers and per-location balances.
- Pin the reviewed runtime and compiled UI for the schema 30 preview.
- Use a compatible pre-upgrade image and data checkpoint for rollback.

## 0.0.0-edge.9

- Recover the caller's original task action using its current recorded task authority, even when
  general operation browsing is disabled; retain the separate browsing permission boundary.
- Enforce shared Unicode code-point limits in task forms, preserve overlong drafts and show the
  field that needs correction; accept the exact limits for astral characters.
- Exercise restricted lost-response recovery and exact Unicode limits in both deployment modes,
  increasing the actual-image campaign to 44 household/task journeys per CPU.
- Replace the earlier Edge.8 candidate with a distinct immutable reviewed runtime.
- Retain schema 9, cold backups and the existing Core API permission scope.

## 0.0.0-edge.8

- Make Tasks the default household screen, with English/Spanish creation, list and detail.
- Claim and complete work as the current participant; approve, reject or reopen the current cycle.
- Review adjustable linked-material quantities without inventing stock or downstream delivery.
- Recover an uncertain original task request through an authorized read, without another command.
- Keep household administration available and move technical task details behind optional disclosure.
- Retain schema 9, cold backups, both CPU families and the existing Core API permission scope.
- Add eight task journeys to the actual-image browser campaign; owner adoption remains separate.

## 0.0.0-edge.7

- Require cold Supervisor backups so the app is stopped while its private SQLite data is copied.
- Document the brief interruption and current-identity revalidation after restart.
- Require explicit stop/backup/state-aware restart when capturing an older preview without this policy.
- Preserve the Edge.6 immutable runtime, schema 9, UI bytes and existing permission scope.
- Keep owner adoption, restore acceptance and required human UX verification pending.

## 0.0.0-edge.6

- Add the English/Spanish household administration workspace for roster, household, member,
  HA mapping/profile, public alias and private preference changes.
- Bind drafts and detached controls to the verified household; preserve exact original revisions
  and require explicit recovery after an uncertain response.
- Include SQLite schema 9 and verified upgrades from the installed Edge.5 schema-7 runtime.
- Preserve original operation history through supported restoration and compatible application/data rollback.
- Freeze Edge.5 independently and exercise the actual pinned Edge.6 image in both CPU jobs.
- Retain the existing private listener, nonroot server and Core API permission scope.
- Mark this configuration/schema boundary as breaking and pin the reviewed source/archive/payload.
- Keep actual owner adoption, required human UX, remaining domains and complete Stable acceptance pending.

## 0.0.0-edge.5

- Translate the technical membership status in both English and Spanish.
- Preserve the setup draft while switching languages with technical details expanded.
- Verify original receipts survive actual browser-tab closure without automatic duplicate work.
- Keep SQLite schema 7 and the existing identity, private listener and Core API permission scope.
- Pin the corrected reviewed source and its verified archive checksum as a distinct immutable build.

## 0.0.0-edge.4

- Add the English/Spanish household entry UI through the existing Ingress session and private listener.
- Require explicit household setup and own membership; retain exact original requests for deliberate recovery.
- Preserve in-flight command evidence when a stale close intent arrives; normal close resumes after completion.
- Build the exact reviewed UI with immutable Node/source inputs and include it in the installed Python wheel.
- Keep Node, browser fixtures and development dependencies out of the runtime image.
- Upgrade verified older data to SQLite schema 7, retaining identity, household records, history and replay guards.
- Mark the schema boundary as breaking; require explicit upgrade and reject old-image downgrade without changing data.
- Keep other domain screens, stable release and complete product acceptance pending.

## 0.0.0-edge.3

- Preserve complete original operation history separately from restored household state in SQLite schema 4.
- Add console-only restore preparation, verification, activation, status and interruption recovery.
- Retain a verified pre-activation source checkpoint; rollback also preserves newer replay evidence.
- Migrate only a verified target during restoration and retain original source data.
- Prevent reusing consumed or canceled recovery approval after restoring an older checkpoint.
- Mark the schema/history boundary as breaking: an older image must not open schema 4 or selected generations.
- Keep the complete product UI, live restore and production acceptance pending.

## 0.0.0-edge.2

- Add private persistent installation identity and SQLite household/member/policy/recovery services.
- Prepare only the app's own private data child, then run the server without root privileges.
- Require one to four fixed Home Assistant browser origins in the app configuration.
- Preserve data and original-operation receipts on restart; keep sessions in memory.
- Include manual snapshot creation/inspection and console-only recovery approval; restore remains pending.
- Keep the full household UI and production acceptance pending.

## 0.0.0-edge.1

- Add the native Home Assistant authentication preview without an additional sign-in.
- Bind the locally built app to reviewed runtime source and locked dependencies.
- Keep household commands, product UI and production acceptance explicitly pending.
