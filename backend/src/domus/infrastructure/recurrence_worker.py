"""One explicitly owned polling thread; stop and join before releasing its data lease."""

import logging
import math
from collections.abc import Callable
from threading import Event, Lock, Thread

from domus.application.fair_recurrence import FixedRun
from domus.domain.errors import DomusError, Forbidden


class MaintenanceWorker[T]:
    def __init__(
        self, tick: Callable[[Callable[[], bool]], T], name: str, *, interval: float = 5.0
    ) -> None:
        if (
            type(interval) not in (int, float)
            or not math.isfinite(interval)
            or not 0 < interval <= 60
        ):
            raise ValueError(f"invalid_{name}_poll_interval")
        self._tick = tick
        self._name = name
        self._interval = interval
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None
        self._closed = False
        self._last_run: T | None = None
        self._last_failure: str | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def last_run(self) -> T | None:
        with self._lock:
            return self._last_run

    @property
    def last_failure(self) -> str | None:
        with self._lock:
            return self._last_failure

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError(f"{self._name}_worker_closed")
            if self._thread is not None:
                return
            thread = Thread(target=self._run, name=f"domus-{self._name}", daemon=False)
            thread.start()
            self._thread = thread

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join()

    def _should_continue(self) -> bool:
        return not self._stop.is_set()

    def _run(self) -> None:
        while self._should_continue():
            try:
                result = self._tick(self._should_continue)
            except Exception as error:
                code = (
                    "scope_denied"
                    if isinstance(error, Forbidden)
                    else f"{self._name}_unavailable"
                    if isinstance(error, DomusError)
                    else "result_unconfirmed"
                )
                with self._lock:
                    self._last_run, self._last_failure = None, code
                logging.getLogger(f"domus.{self._name}").warning(
                    "%s_run_unconfirmed code=%s", self._name, code
                )
                if isinstance(error, Forbidden):
                    return
            else:
                with self._lock:
                    self._last_run, self._last_failure = result, None
            if self._stop.wait(self._interval):
                return


class RecurrenceWorker(MaintenanceWorker[FixedRun]):
    def __init__(
        self, tick: Callable[[Callable[[], bool]], FixedRun], *, interval: float = 5.0
    ) -> None:
        super().__init__(tick, "recurrence", interval=interval)
