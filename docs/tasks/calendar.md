# Protected household calendar

Open **Calendar** in the household navigation in Ingress or standalone. Choose Month, Week,
Day or Agenda and a reference date, then select **Show calendar**. Agenda lists entries by
date and fits narrow displays. Select **Only my entries** to see work assigned to you, work
you performed, or work you verified. **More entries** loads the next page for the selected
range and filters. Calendar reads do not change the task or advance recurrence processing.

For API clients, send the verified `X-Domus-Context` when requesting `GET /api/v1/tasks/calendar`. The endpoint uses
current local task-read authority and the existing session boundary.

Supply `start` and `end` as local ISO dates. The half-open range can cover one to 366 days.
Filter by entry kind, task timing, status, priority, an active household category or
household member. The page and both counts use the same filters. Member filters use assignees for planned and due work,
performers for actual work, and the verifier for an approval.

In **Tasks**, task administrators can create, rename and archive household categories.
Use a name of 1–80 characters. Active names are unique after trimming, Unicode
normalization and case folding. If the result is uncertain, choose **Check saved
request** to retrieve the original result before starting another change.

Choose an active **Category** when creating an ordinary or scheduled task, or keep
**Unclassified**. Existing tags remain independent. Renaming or archiving changes the
available choices. Existing task and calendar entries keep the category label captured
with that work. If a category becomes unavailable while you are writing a task, select
an active category or **Unclassified**. The title, description and schedule draft stay
in the form. If a category edit conflicts, review the current revision before saving
the draft again.

The API category filter accepts the active category ID. An archived or foreign ID
fails before any filtered entries or counts are disclosed. The native Home Assistant
entity keeps its reduced projection.

The entries distinguish original planned time, the effective due date, performed time and
approval time. Date-only entries have a local date and no instant or time of day. If a
task was rescheduled, its original plan and effective deadline can appear on different days.
A timed planned entry carries the original nominal value and the resolved local value, including
a daylight-saving adjustment. Other instants are presented in the household's time zone.

Follow `next_cursor` with the original range, filters and page size. The cursor expires after
five minutes and belongs to the verified principal and local authority context. A pending
projection can return valid entries while additional recurrence sources still need processing.

**My week starts on** selects Monday or Sunday for the current member. It changes week
ranges and month column alignment. The default is Monday. Each member's choice has its
own revision and is private, including when another member administers the household.
If a save response is lost, use **Check original week-start change** before changing the
preference again. Signing out clears the saved request from the browser.

The protected calendar also exposes `GET /api/v1/tasks/calendar/home-assistant` with
the same date range, filters, page size and current task-read grant. Each event's
`uid` is the calendar `entry_id`. A date-only event uses an ISO local date. Timed
events carry the actual local offset, including for resolved daylight-saving transitions.
The page retains the pending state and the source cursor. An unavailable source returns
an error. External synchronization is disabled.

The [Home Assistant integration design](../../specs/home-assistant-surface.md) covers
registration of native calendar entities and the installation credential.

For a read-only calendar entity in Home Assistant, see
[Connect the native Home Assistant calendar](ha-calendar.md).

The matching entry count includes each planned, due, performed or approval
entry. The matching task count includes each distinct occurrence once. Both
counts cover the complete filtered range across all pages.
