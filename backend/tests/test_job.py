import subprocess
import sys
import time

import pytest

from agentic_os.__main__ import pid_exists

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects")

# A "backend" that joins the kill-on-close job, starts a long-lived grandchild and waits.
PARENT = (
    "import subprocess, sys, time\n"
    "from agentic_os.services.pty.job import kill_children_on_exit\n"
    "assert kill_children_on_exit()\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(120)\n"
)


def test_children_die_when_the_job_owner_is_killed():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline())
    assert pid_exists(child_pid)

    parent.kill()  # TerminateProcess: no cleanup code runs in the parent
    parent.wait(10)

    deadline = time.monotonic() + 10
    while pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not pid_exists(child_pid)
