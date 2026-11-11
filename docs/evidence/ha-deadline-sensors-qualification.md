# Native task deadline sensors qualification

[Issue #112](https://github.com/vypdev/domus/issues/112) projects the
same two deadline counts as Overview. The native calendar and deadline
counts have independent grants and configuration entries.

| Published case | Executable evidence |
| --- | --- |
| `domus-ha-deadline-sensors-C01` | The [Overview tests](../../tests/backend/test_task_overview.py) compare the installation query with the protected member view across exact timed boundaries and saved fixed and relative date-only policies. |
| `domus-ha-deadline-sensors-C02` | The [installation tests](../../tests/backend/test_ha_deadline_installation.py) distinguish a successful empty household from an absent household. The [Core tests](../../tests/ha/calendar_smoke.py) exercise invalid, unavailable and recovered snapshots and show both native states. |
| `domus-ha-deadline-sensors-C03` | The Core tests verify registration, duplicate rejection, retained entity IDs through entry reload and a new Core process, and distinct identities for both channels and installations. |
| `domus-ha-deadline-sensors-C04` | The installation and Core tests exercise grant isolation on the private Supervisor listener and standalone HTTPS, and reject unsupported methods and unrelated credentials. |
| `domus-ha-deadline-sensors-C05` | The installation tests exercise replacement and removal of the digest on both transports. Core verifies the existing entity IDs survive rotation and reconfiguration. |
| `domus-ha-deadline-sensors-C06` | One Core refresh updates both entities. Oversized and malformed replies fail. The native lifecycle test verifies polling stops after unload. |
| `domus-ha-deadline-sensors-C07` | The [packaged composition tests](../../tests/containers/test_app_image.py) connect sensors and the calendar together with their existing credentials, event identities and native reads. |
| `domus-ha-deadline-sensors-C08` | The packaged tests exercise Core 2026.10.4 with the Ingress and standalone images. The [operator guide](../tasks/ha-deadline-sensors.md) covers setup and recovery in English and Spanish. |

The increment uses the existing SQLite schema and preserves the native calendar
configuration. The release candidate's installed walkthrough is recorded
separately from the disposable Core tests.
