"""Real disposable stdio workers prove framing, bounded I/O and no automatic mutation replay."""

import json
import runpy
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
ImageChannel = runpy.run_path(str(ROOT / "tests/browser/image_channel.py"))["ImageChannel"]
ECHO = (
    "import sys,json,os\nfor line in sys.stdin:\n value=json.loads(line); pri"
    "nt(json.dumps({'transport_id':value['transport_id'],'response':{'pid':"
    "os.getpid(),'value':value['request']}}),flush=True)"
)


def worker(script=ECHO, **options):
    return ImageChannel([sys.executable, "-u", "-c", script], **options)


def test_one_real_worker_preserves_large_exact_frames_and_concurrent_contexts():
    channel = worker()
    values = [
        {"key": str(index), "body": "λ" * 2**18, "revision": "9007199254740993"}
        for index in range(4)
    ]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda value: json.loads(channel.exchange(value)), values))
        assert [reply["value"] for reply in replies] == values
        assert {reply["pid"] for reply in replies} == {channel.process.pid}
        assert channel.process.poll() is None
    finally:
        channel.close()
    assert channel.process.poll() is not None
    assert channel.process.stdin.closed and channel.process.stdout.closed
    channel.close()
    with pytest.raises(ValueError, match="no longer available"):
        channel.exchange({"key": "must-not-resend"})


@pytest.mark.parametrize(
    "output", ["print('x'*40)", "import os; os.write(1,b'{}\\n{}\\n')", "print('{}',end='')"]
)
def test_incomplete_excessive_or_unsolicited_response_closes_without_restarting(output):
    starts = []

    def launch(*args, **kwargs):
        result = subprocess.Popen(*args, **kwargs)
        starts.append(result)
        return result

    channel = worker("import sys\nsys.stdin.readline()\n" + output, launcher=launch, frame_limit=32)
    with pytest.raises(ValueError):
        channel.exchange({"original_key": "once"})
    assert channel.closed and len(starts) == 1 and starts[0].poll() is not None
    with pytest.raises(ValueError):
        channel.exchange({"original_key": "once"})
    assert len(starts) == 1


def test_read_deadline_closes_the_worker_and_does_not_retry_the_original_request():
    def ready(reads, writes, errors, timeout):
        assert 0 < timeout <= 30
        return [], writes, []

    channel = worker(wait=ready)
    with pytest.raises(subprocess.TimeoutExpired):
        channel.exchange({"original_key": "uncertain"})
    assert channel.closed and channel.process.poll() is not None


def test_write_deadline_closes_without_writing_or_retrying():
    channel = worker(wait=lambda *args: ([], [], []))
    with pytest.raises(subprocess.TimeoutExpired):
        channel.exchange({"original_key": "not-sent"})
    assert channel.closed and channel.process.poll() is not None


def test_close_forces_only_its_owned_stubborn_process_and_is_idempotent():
    calls = []

    class Process:
        def __init__(self):
            self.stdin, self.stdout = TemporaryFile(), TemporaryFile()

        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, *, timeout):
            calls.append("wait")
            if calls.count("wait") == 1:
                raise subprocess.TimeoutExpired("owned-fixture", timeout)
            return 0

        def kill(self):
            calls.append("kill")

    process = Process()
    channel = ImageChannel(["owned-fixture"], launcher=lambda *args, **kwargs: process)
    channel.close()
    channel.close()
    assert process.stdin.closed and process.stdout.closed
    assert calls == ["terminate", "wait", "kill", "wait"]


@pytest.mark.parametrize("identity", [0, True, 1.0, "1"])
def test_wrong_frame_identity_cannot_be_reported_as_the_current_original_result(identity):
    channel = worker(
        "import sys,json\nsys.stdin.readline()\nprint(json.dumps({'transport_id':"
        + repr(identity)
        + ",'response':{'status':200}}))"
    )
    with pytest.raises(ValueError, match="identity"):
        channel.exchange({"original_key": "different-current-context"})
    assert channel.closed and channel.process.poll() is not None


def test_a_queued_request_timeout_does_not_close_or_resend_another_context():
    channel = worker()
    channel.lock.acquire()
    try:
        channel.timeout = 0
        with pytest.raises(subprocess.TimeoutExpired):
            channel.exchange({"original_key": "not-sent"})
        assert not channel.closed and channel.process.poll() is None
    finally:
        channel.lock.release()
    try:
        channel.timeout = 30
        reply = json.loads(channel.exchange({"original_key": "later-explicit-request"}))
        assert reply["value"] == {"original_key": "later-explicit-request"}
        assert channel.sequence == 1
    finally:
        channel.close()
