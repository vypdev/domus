"""One owned stdio worker carries exact framed requests without restarting or resending them."""

import contextlib
import json
import os
import select
import subprocess
import threading
import time


class ImageChannel:
    def __init__(
        self,
        command,
        *,
        launcher=subprocess.Popen,
        wait=select.select,
        timeout=30,
        frame_limit=2**24,
    ):
        self.command = tuple(command)
        self.wait, self.timeout, self.frame_limit = wait, timeout, frame_limit
        self.lock, self.close_lock, self.closed = threading.Lock(), threading.Lock(), False
        self.sequence = 0
        self.process = launcher(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        assert self.process.stdin is not None and self.process.stdout is not None
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)

    def exchange(self, value):
        if not self.lock.acquire(timeout=self.timeout):
            raise subprocess.TimeoutExpired(self.command, self.timeout)
        try:
            if self.closed or self.process.poll() is not None:
                raise ValueError("The image transport worker is no longer available")
            deadline = time.monotonic() + self.timeout
            self.sequence += 1
            payload = json.dumps({"transport_id": self.sequence, "request": value}).encode() + b"\n"
            incoming, outgoing = self.process.stdout.fileno(), self.process.stdin.fileno()
            while payload:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.wait([], [outgoing], [], remaining)[1]:
                    raise subprocess.TimeoutExpired(self.command, self.timeout)
                try:
                    written = os.write(outgoing, payload)
                except BlockingIOError:
                    continue
                if written == 0:
                    raise ValueError("The image transport worker accepted no request bytes")
                payload = payload[written:]
            response = bytearray()
            while b"\n" not in response:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.wait([incoming], [], [], remaining)[0]:
                    raise subprocess.TimeoutExpired(self.command, self.timeout)
                try:
                    part = os.read(incoming, min(65536, self.frame_limit + 1 - len(response)))
                except BlockingIOError:
                    continue
                if not part:
                    raise ValueError("The image transport worker ended without a complete response")
                response.extend(part)
                if len(response) > self.frame_limit:
                    raise ValueError("The image transport response exceeds its frame budget")
            if response.count(b"\n") != 1 or not response.endswith(b"\n"):
                raise ValueError("The image transport returned unsolicited response bytes")
            frame = json.loads(response[:-1])
            if (
                not isinstance(frame, dict)
                or set(frame) != {"transport_id", "response"}
                or type(frame["transport_id"]) is not int
                or frame["transport_id"] != self.sequence
            ):
                raise ValueError("The image transport response identity differs from its request")
            return json.dumps(frame["response"])
        except BaseException:
            self.close()
            raise
        finally:
            self.lock.release()

    def close(self):
        with self.close_lock:
            if not self.closed:
                self.closed = True
                for stream in (self.process.stdin, self.process.stdout):
                    with contextlib.suppress(OSError):
                        stream.close()
                if self.process.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
