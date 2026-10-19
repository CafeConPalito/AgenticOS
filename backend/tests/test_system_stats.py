"""The machine's load while documents are processed (phase 14, spike S8)."""

import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from agentic_os.services.system_stats import GpuProbe, Sampler, SamplerThread, gpu_load

LUID_A = "0x00000000_0x0000D3E8"  # an adapter
LUID_B = "0x00000000_0x0000D3F9"  # another one


def engine(pid: int, luid: str, kind: str, phys: int = 0) -> str:
    return f"pid_{pid}_luid_{luid}_phys_{phys}_eng_0_engtype_{kind}"


def test_the_gpu_figure_is_the_busiest_engine_of_the_busiest_adapter():
    readings = {
        engine(10, LUID_A, "3D"): 30.0,
        engine(11, LUID_A, "3D"): 25.0,  # two processes share the 3D engine of adapter A: 55
        engine(10, LUID_A, "Copy"): 5.0,
        engine(12, LUID_B, "Compute_0"): 80.0,
        "garbage": 99.0,
    }
    total, mine = gpu_load(readings, pids={10})
    assert (total, mine) == (80.0, 0.0)  # adapter B is busier and none of it is ours
    total, mine = gpu_load(readings, pids={12})
    assert (total, mine) == (80.0, 80.0)
    total, mine = gpu_load({k: v for k, v in readings.items() if LUID_B not in k}, pids={10, 11})
    assert (total, mine) == (55.0, 55.0)


def test_no_readings_is_an_idle_gpu():
    assert gpu_load({}, set()) == (0.0, 0.0)
    assert gpu_load({engine(1, LUID_A, "3D"): 250.0}, {1}) == (100.0, 100.0)  # never above 100


class FakeGpu:
    def __init__(self, readings):
        self.readings, self.closed = readings, False

    def read(self):
        return self.readings

    def close(self):
        self.closed = True


def test_a_sample_has_the_machine_and_the_apps_share():
    sampler = Sampler(gpu=FakeGpu({engine(1, LUID_A, "3D"): 12.5}))
    time.sleep(0.2)
    sample = sampler.sample()
    cpu, memory = sample["cpu"], sample["memory"]
    assert 0 <= cpu["percent"] <= 100 and 0 <= cpu["app_percent"] <= 100 and cpu["cores"] >= 1
    assert memory["total_mb"] > 0 and memory["app_mb"] > 0
    assert 0 <= memory["percent"] <= 100
    assert sample["gpu"] == {"percent": 12.5, "app_percent": 0.0}  # pid 1 is not ours
    sampler.close()


def test_a_gpu_that_cannot_be_read_is_not_available_not_an_error():
    class Broken(FakeGpu):
        def read(self):
            raise OSError("counter gone")

    assert Sampler(gpu=Broken({})).sample()["gpu"] is None
    assert Sampler(gpu=False).sample()["gpu"] is None


def test_the_app_share_includes_the_processes_it_started():
    import subprocess

    sampler = Sampler(gpu=False)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time\nt=time.time()\nwhile time.time()-t<3: pass"]
    )
    try:
        time.sleep(1.0)
        sampler.sample()  # prime the rates of the new process
        time.sleep(1.0)
        sample = sampler.sample()
    finally:
        child.kill()
        child.wait()
    assert sample["cpu"]["app_percent"] > 0  # the busy child counts as the app's
    assert sample["memory"]["app_mb"] > 0


def test_samples_are_published_only_while_there_is_work():
    published = []
    busy = threading.Event()
    thread = SamplerThread(published.append, busy.is_set, Sampler(gpu=False), interval=0.05)
    thread.start()
    try:
        time.sleep(0.3)
        assert published == []  # idle: nothing is measured
        busy.set()
        deadline = time.monotonic() + 3
        while not published and time.monotonic() < deadline:
            time.sleep(0.05)
        assert published and published[0]["type"] == "system"
        assert set(published[0]) >= {"cpu", "memory", "gpu"}
        busy.clear()
        time.sleep(0.2)
        count = len(published)
        time.sleep(0.3)
        assert len(published) == count  # and stops again
    finally:
        thread.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="the GPU counters are a Windows feature")
def test_the_real_gpu_counter_reads_on_windows():
    try:
        probe = GpuProbe()
    except OSError:
        pytest.skip("this machine has no GPU engine counters")
    try:
        time.sleep(0.5)
        readings = probe.read()
        assert isinstance(readings, dict)
        assert all(isinstance(v, float) for v in readings.values())
    finally:
        probe.close()


def test_the_api_gives_one_reading(client: TestClient):
    body = client.get("/api/knowledge/system").json()
    assert set(body) == {"cpu", "memory", "gpu"}
    assert body["memory"]["total_mb"] > 0
