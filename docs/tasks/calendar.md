# Protected household calendar

The calendar reads the same household and task records in Ingress and standalone. Send the
verified `X-Domus-Context` when requesting `GET /api/v1/tasks/calendar`. The endpoint uses
current local task-read authority and the existing session boundary.

Supply `start` and `end` as local ISO dates. The half-open range can cover one to 366 days.
Filter by entry kind, task timing, status, priority, category tag or household member. The
count and page use the same filters. Member filters use assignees for planned and due work,
performers for actual work, and the verifier for an approval.

The entries distinguish original planned time, the effective due date, performed time and
approval time. Date-only entries have a local date and no instant or time of day. If a
task was rescheduled, its original plan and effective deadline can appear on different days.
A timed planned entry carries the original nominal value and the resolved local value, including
a daylight-saving adjustment. Other instants are presented in the household's time zone.

Follow `next_cursor` with the original range, filters and page size. The cursor expires after
five minutes and belongs to the verified principal and local authority context. A pending
projection can return valid entries while additional recurrence sources still need processing.
