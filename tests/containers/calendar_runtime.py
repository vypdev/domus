"""Disposable installed-runtime seed for the packaged calendar acceptance."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn

from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CreateTask, CreateTaskOccurrence
from domus.composition.server import create_owned_runtime
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_rules import FixedPattern, Frequency, NominalDate
from domus.domain.recurrence_time import TimePolicy
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

ROOT = Path("/data/domus")
RUNTIME_UID = 65532


class Actor:
    def current(self):
        return HumanIdentity("calendar-fixture-admin", True, True, False)

    def get(self, _identifier):
        raise AssertionError("The seed does not query a human directory")


def seed(channel, label):
    with closing(open_storage(ROOT, channel)) as storage:
        store = storage.database
        clock, identifiers, actor = SystemClock(), SecureIdentifiers(), Actor()
        HouseholdCommands(store, actor, actor, TimeZoneCatalog(), clock, identifiers).setup(
            "fixture-household", SetupHousehold(label, "UTC")
        )
        tasks = TaskCommands(store, actor, clock, identifiers)
        created = tasks.create("fixture-task", CreateTask(TaskContent(f"{label} deadline")))
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        due_at = int(tomorrow.timestamp() * 1000)
        tasks.create_occurrence(
            "fixture-due",
            CreateTaskOccurrence(created.result.decode()["definition_id"], due_at=due_at),
        )
        tasks.create_occurrence(
            "fixture-overdue",
            CreateTaskOccurrence(created.result.decode()["definition_id"], due_at=1),
        )
        times = PinnedRecurrenceTime()
        rule = FixedPattern(NominalDate(tomorrow.date()), Frequency.DAILY, count=1)
        RecurrenceCommands(
            store,
            actor,
            clock,
            identifiers,
            FixedRecurrencePlanner(CalendarNominalExpansion(), times),
        ).create_fixed(
            "fixture-rule",
            CreateFixedTask(
                CreateTask(TaskContent(f"{label} plan")),
                rule,
                TimePolicy("UTC", times.data_identity),
            ),
        )
        print(storage.installation.instance_id)


def owned_path(path):
    path.mkdir(mode=0o700, parents=True)
    os.chown(path, RUNTIME_UID, RUNTIME_UID)


def serve(mode, channel, host, config_path):
    os.umask(0o077)
    ROOT.parent.mkdir(exist_ok=True)
    ROOT.parent.chmod(0o755)
    owned_path(ROOT)
    label = f"{mode} {channel}"
    completed = subprocess.run(
        [sys.executable, __file__, "seed", channel, label],
        user=RUNTIME_UID,
        group=RUNTIME_UID,
        extra_groups=[],
        capture_output=True,
        check=True,
        text=True,
        timeout=12,
    )
    instance = completed.stdout.strip()
    digest = hashlib.sha256(f"{instance}.{channel}.{'d' * 64}".encode("ascii")).hexdigest()
    deadline_digest = hashlib.sha256(
        f"{instance}.{channel}.deadlines.{'e' * 64}".encode("ascii")
    ).hexdigest()
    if mode == "native":
        config = json.loads(Path(config_path).read_text())
        options = {
            **config["options"],
            "ha_calendar_digest": digest,
            "ha_deadline_digest": deadline_digest,
        }
        Path("/data/options.json").write_text(json.dumps(options))
        launcher = "/app/.venv/bin/domus-ha-app"
        os.environ["SUPERVISOR_TOKEN"] = "disposable-supervisor-token"
        os.execv(launcher, [launcher, "--channel", channel])
    tls = Path("/tmp/calendar-tls")
    owned_path(tls)
    for name in ("cert.pem", "key.pem"):
        target = tls / name
        shutil.copyfile(Path("/tls") / name, target)
        os.chown(target, RUNTIME_UID, RUNTIME_UID)
    os.setgroups([])
    os.setgid(RUNTIME_UID)
    os.setuid(RUNTIME_UID)
    runtime = create_owned_runtime(
        "https://ha.fixture",
        f"https://{host}:8443",
        channel,
        ROOT,
        ha_calendar_digest=digest,
        ha_deadline_digest=deadline_digest,
    )
    try:
        uvicorn.run(
            runtime.app,
            host="0.0.0.0",
            port=8443,
            proxy_headers=False,
            access_log=False,
            ssl_certfile=str(tls / "cert.pem"),
            ssl_keyfile=str(tls / "key.pem"),
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    if sys.argv[1] == "seed":
        seed(*sys.argv[2:])
    else:
        serve(*sys.argv[1:])
