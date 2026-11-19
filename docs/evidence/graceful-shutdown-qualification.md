# Requested process shutdown qualification

[Domus #139](https://github.com/vypdev/domus/issues/139) corrects requested SIGTERM
handling in the native and standalone CLI entrypoints. The existing contract is
in [configuration](../configuration.md),
[identity and storage operations](../operations-identity-storage.md) and the
worker-lifetime section of the
[recurrence continuation specification](../../specs/recurrence-storage-continuation.md).
Cleanup contributes to `platform-foundation-identity-sqlite-C31`, with restart
and durable receipt evidence contributing to C39 and C55 of the
[identity and SQLite specification](../../specs/platform-foundation-identity-sqlite.md).

## Confirmed regression

The independently installed Edge.46 app showed `Error` after a requested stop.
Exact-image probes used a read-only entrypoint wrapper to observe entry and
completion of the unchanged packaged runtime close. SIGTERM exited 143 and
omitted both markers in default and projection-enabled native and standalone
configurations. SIGINT controls completed runtime close in all four configurations.
The owner's exact exit code remains unobserved.

Uvicorn restores and replays its captured signals after ASGI shutdown. The
original SIGTERM disposition terminated the process before the CLI's outer
`finally` could complete runtime close. The CLI now converts that requested
termination into controlled unwinding, completes cleanup, and returns zero.
It defers subsequent SIGTERM requests during cleanup and restores the prior
signal disposition on return.

## Case evidence

| Behavior | Verification |
| --- | --- |
| Requested termination | Both native listener paths and standalone execute explicit runtime close through the actual CLI. |
| Repeated signals | Three further SIGTERM requests during the observed cleanup gate allow cleanup to finish and the process to exit zero. |
| Owned lifetime | Actual ASGI workers have stopped before runtime close. Successful restart reopens the owned installation lease. |
| Identity cleanup | A disposable standalone provider supplies three synthetic grants. Every local session is removed before remote cleanup. Exactly two revocations are attempted, including one unavailable response, and the reported result is one confirmed and two unconfirmed grants. |
| Persistent state | Two restarts retain the installation identity and the exact original task operation and result. |
| Interrupted composition | Unit regressions stop native and standalone composition after storage opens and verify that the same installation can be reopened. |
| Listener handoff | Unit regressions request termination after runtime creation and before the listener starts. Both compositions close the constructed runtime. |
| Error reporting | Listener errors, keyboard interruption and cleanup failures propagate through the signal scope, which restores the original handler. Configuration-error tests cover invalid startup input. |

The new actual-image regression fails against immutable Edge.46 because SIGTERM
skips explicit close. The corrected immutable Edge.47 ARM64 image passed all four
regression cases, including twelve requested stops and eight restarts. All four
pinned-package checks passed, covering every Python and UI file, native authority
and restart, private standalone delivery, and an actual Edge.5 upgrade and restore.
The separate real-Core case passed all four packaged deployment compositions.

The immutable runtime source is `6e35e7e97926753adea78e40b9669f4fd2a01d54`.
Its source archive SHA-256 is
`d1bfb1c259bcf87c3531da91ed7faebf75272c66f24ec69c05ab357f5bbd88dc`.
The wheel SHA-256 is
`7695249a943695ab603f753c4976cd0d953dd6c3e945e0bba61ec7960423a12c`.
The local ARM64 image is
`sha256:fa0964010fe5b0420bed3268084e7080356b208852467e5cfb780541396085a3`.
Its 231 Python files and four UI files match the
[artifact declaration](../../addon-edge/artifact.json) exactly.

The signal scope has 21 statements and two branches. The focused CLI campaign
passed 28 cases, including the startup and listener-handoff regressions. The full
backend campaign passed 5,509 cases with all 231 authored modules at 100% statement
and branch coverage, covering 17,900 statements and 4,832 branches. The independent
source and per-file audit passed.
Architecture and tooling passed 237 cases, strict mypy passed all 231 source files,
and Ruff and documentation checks passed.

Exact-head CI, both image architectures and separately installed corrected Edge
acceptance are final gates.
