import os
import sys
import threading
import time

from agentic_os.services.pty import spawn

ECHO = (
    "import sys\n"
    "print('READY', flush=True)\n"
    "line = sys.stdin.readline()\n"
    "print('GOT:' + line.strip(), flush=True)\n"
    "sys.exit(3)\n"
)


def collect(proc, until: str, timeout: float = 15) -> str:
    out: list[str] = []
    done = threading.Event()

    def reader() -> None:
        while not done.is_set():
            chunk = proc.read()
            if not chunk:
                break
            out.append(chunk)
            if until in "".join(out):
                break
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(timeout)
    return "".join(out)


def test_spawn_read_write_and_exit_code(tmp_path):
    proc = spawn([sys.executable, "-c", ECHO], str(tmp_path), dict(os.environ), 100, 30)
    try:
        assert "READY" in collect(proc, "READY")
        proc.write("hola\r")
        assert "GOT:hola" in collect(proc, "GOT:hola")
        deadline = time.monotonic() + 10
        while proc.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not proc.is_alive()
        assert proc.exit_code == 3
    finally:
        proc.terminate()


def test_terminate_kills_a_blocked_process(tmp_path):
    proc = spawn(
        [sys.executable, "-c", "import time; time.sleep(60)"], str(tmp_path), dict(os.environ)
    )
    assert proc.is_alive()
    proc.resize(80, 24)  # must not raise on a live process
    proc.terminate()
    deadline = time.monotonic() + 10
    while proc.is_alive() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not proc.is_alive()
