# Shared domain glossary

| Term | Meaning and owner |
|---|---|
| Household | One installation's scope for records and permissions |
| Principal | Verified human or technical identity; never a caller-supplied name |
| Member | Household participant linked to their own distinct HA account |
| HA person | Optional presence/profile entity; not an authentication credential |
| Task definition | Reusable responsibility, policy and version |
| Task occurrence | A specific execution with stable identity and independent history |
| Assignee | Planned responsible member |
| Actual performer | Member who did the work; may differ from the assignee |
| Completion actor | Authenticated principal recording completion |
| Verifier | Authorized principal approving completion when required |
| Due date | Deadline; distinct from scheduled start and actual completion |
| Demand | Attributable purchasing intent with additional/overlapping semantics |
| Shopping line | Reversible aggregation of compatible demands, retaining sources |
| Purchase | Recorded acquisition commitment; not proof of physical receipt |
| Receipt | Confirmed physically received quantity |
| Product | Identity of a supply, independent of package presentation |
| Presentation | Package size and exact conversion to the product base unit |
| Stock movement | Immutable receipt, consumption, transfer or correction entry |
| Reservation | Stock allocated to a material requirement |
| Available stock | Physical stock minus active reservations |
| Points entry | Immutable award, reversal or correction with a unique source |
| Base task points | Nominal task value before the selected collaborative allocation policy |
| Actual awarded total | Sum of immutable performer shares; may differ from base points according to the configured policy |
| Allocation policy | Versioned household rule for conserving, rounding, decimal, full-performer or authorized manual awards |
| Outbox / inbox | Durable event publication and deduplicated consumption records |
| Projection | Rebuildable read model; not another source of business truth |
| Stable | Production channel with a versioned accepted artifact |
| Edge | Experimental channel, isolated from production data and credentials |
| CI Check | Project-owned verification workflow; separate from immutable Copilot automation |
| Dogfooding | Controlled real use in the owner's local HA through Google Chrome |
