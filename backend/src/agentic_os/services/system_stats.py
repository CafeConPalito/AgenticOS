"""How loaded the machine is while documents are processed (phase 14, spike S8): CPU, memory and
GPU of the whole computer and the share that belongs to the app and the processes it started
(the knowledge worker, `llama-server`).

CPU and memory come from `psutil`. The GPU, of any maker, from the Windows performance counter
«GPU Engine»; where it cannot be read the value is `None` and the UI says «not available»."""

from __future__ import annotations

import contextlib
import ctypes
import re
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes

import psutil
import structlog

log = structlog.get_logger()

PDH_FMT_DOUBLE = 0x200
PDH_MORE_DATA = 0x800007D2
_ENGINE = re.compile(r"pid_(\d+)_luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+).*engtype_(\w+)")


class GpuProbe:
    """Reads «GPU Engine - Utilization Percentage». Windows only; no permissions needed."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("the GPU counters are a Windows feature")

        class Value(ctypes.Structure):
            _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

        class Item(ctypes.Structure):
            _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", Value)]

        self._item = Item
        pdh = ctypes.WinDLL("pdh.dll")
        pdh.PdhOpenQueryW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_size_t,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        pdh.PdhAddEnglishCounterW.argtypes = [
            wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)
        ]  # fmt: skip
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
        ]  # fmt: skip
        pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        for name in (
            "PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
            "PdhGetFormattedCounterArrayW", "PdhCloseQuery",
        ):  # fmt: skip
            getattr(pdh, name).restype = ctypes.c_ulong
        self._pdh = pdh
        self._query = wintypes.HANDLE()
        self._counter = wintypes.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
            raise OSError("PdhOpenQuery failed")
        code = pdh.PdhAddEnglishCounterW(
            self._query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(self._counter)
        )
        if code != 0:
            pdh.PdhCloseQuery(self._query)
            raise OSError(f"the GPU counter is not available (0x{code:x})")
        pdh.PdhCollectQueryData(self._query)  # a rate needs two readings: this is the first

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pdh.PdhCloseQuery(self._query)

    def read(self) -> dict[str, float]:
        """{instance name: percent} since the previous reading."""
        pdh = self._pdh
        pdh.PdhCollectQueryData(self._query)
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        code = pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None
        )
        if code != PDH_MORE_DATA:
            return {}
        buffer = ctypes.create_string_buffer(size.value)
        code = pdh.PdhGetFormattedCounterArrayW(
            self._counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buffer
        )
        if code != 0:
            return {}
        items = ctypes.cast(buffer, ctypes.POINTER(self._item))
        return {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value)}


def gpu_load(readings: dict[str, float], pids: set[int]) -> tuple[float, float]:
    """(busiest engine of the busiest adapter, the share of our processes in it) in percent.
    Like Task Manager, the machine's figure is the busiest kind of engine (3D, compute, copy,
    video…) of each adapter, and the busiest adapter."""
    engines: dict[tuple[str, str], float] = {}
    ours: dict[tuple[str, str], float] = {}
    for name, value in readings.items():
        match = _ENGINE.search(name)
        if not match:
            continue
        key = (match.group(2), match.group(3))
        engines[key] = engines.get(key, 0.0) + value
        if int(match.group(1)) in pids:
            ours[key] = ours.get(key, 0.0) + value
    if not engines:
        return 0.0, 0.0
    busiest = max(engines, key=engines.get)
    return min(100.0, engines[busiest]), min(100.0, ours.get(busiest, 0.0))


class Sampler:
    """One measurement of the machine and of our process tree, whenever asked."""

    def __init__(self, gpu: GpuProbe | bool | None = True) -> None:
        self._me = psutil.Process()
        self._known: dict[int, psutil.Process] = {}
        self._cores = psutil.cpu_count() or 1
        self._gpu: GpuProbe | None = None
        if gpu is True:
            try:
                self._gpu = GpuProbe()
            except Exception as error:
                log.info("gpu_counter_unavailable", reason=str(error))
        elif gpu:
            self._gpu = gpu
        psutil.cpu_percent(None)  # prime: the first reading of a rate is meaningless
        self._tree()

    def close(self) -> None:
        if self._gpu:
            self._gpu.close()

    def _tree(self) -> list[psutil.Process]:
        """Us and everything we started, keeping the objects (a rate needs the previous call)."""
        alive: dict[int, psutil.Process] = {self._me.pid: self._me}
        with contextlib.suppress(psutil.Error):
            for child in self._me.children(recursive=True):
                alive[child.pid] = self._known.get(child.pid) or child
        self._known = alive
        return list(alive.values())

    def sample(self) -> dict:
        tree = self._tree()
        app_cpu, app_memory = 0.0, 0
        for process in tree:
            with contextlib.suppress(psutil.Error):
                app_cpu += process.cpu_percent(None)
                app_memory += process.memory_info().rss
        memory = psutil.virtual_memory()
        gpu: dict | None = None
        if self._gpu is not None:
            try:
                total, mine = gpu_load(self._gpu.read(), {p.pid for p in tree})
                gpu = {"percent": round(total, 1), "app_percent": round(mine, 1)}
            except Exception as error:
                log.info("gpu_counter_failed", reason=str(error))
        return {
            "cpu": {
                "percent": round(psutil.cpu_percent(None), 1),
                # psutil counts one core as 100 %: the share of the whole machine.
                "app_percent": round(min(100.0, app_cpu / self._cores), 1),
                "cores": self._cores,
            },
            "memory": {
                "percent": round(memory.percent, 1),
                "used_mb": round((memory.total - memory.available) / 2**20),
                "total_mb": round(memory.total / 2**20),
                "app_mb": round(app_memory / 2**20),
            },
            "gpu": gpu,  # None: not available on this computer
        }


class SamplerThread:
    """Publishes a sample every second while `is_busy()` says there is work."""

    def __init__(
        self,
        publish: Callable[[dict], None],
        is_busy: Callable[[], bool],
        sampler: Sampler | None = None,
        interval: float = 1.0,
    ) -> None:
        self._publish = publish
        self._busy = is_busy
        self._sampler = sampler
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="system-stats", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        if self._sampler:
            self._sampler.close()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            if not self._busy():
                continue
            if self._sampler is None:
                self._sampler = Sampler()  # created when the first work comes
            with contextlib.suppress(Exception):
                self._publish({"type": "system", **self._sampler.sample()})
