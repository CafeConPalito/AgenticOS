"""S8a: GPU utilisation of any vendor on Windows via the PDH counter "GPU Engine - Utilization Percentage"."""

import ctypes
import re
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8")

pdh = ctypes.WinDLL("pdh.dll")
PDH_FMT_DOUBLE = 0x200
PDH_MORE_DATA = 0x800007D2


class VALUE(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class ITEM(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", VALUE)]


class GpuProbe:
    def __init__(self):
        self.query = wintypes.HANDLE()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) != 0:
            raise OSError("PdhOpenQuery failed")
        self.counter = wintypes.HANDLE()
        rc = pdh.PdhAddEnglishCounterW(
            self.query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(self.counter)
        )
        if rc != 0:
            raise OSError(f"PdhAddEnglishCounter failed 0x{rc & 0xFFFFFFFF:x}")
        pdh.PdhCollectQueryData(self.query)

    def sample(self):
        """-> {instance name: percent}"""
        pdh.PdhCollectQueryData(self.query)
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        rc = pdh.PdhGetFormattedCounterArrayW(
            self.counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None
        )
        if (rc & 0xFFFFFFFF) != PDH_MORE_DATA:
            return {}
        buf = ctypes.create_string_buffer(size.value)
        rc = pdh.PdhGetFormattedCounterArrayW(
            self.counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf
        )
        if rc != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(ITEM))
        return {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value)}


def summarize(sample, pids=()):
    by_type = {}
    mine = 0.0
    for name, val in sample.items():
        m = re.search(r"pid_(\d+).*engtype_(\w+)", name)
        if not m:
            continue
        pid, typ = int(m.group(1)), m.group(2)
        by_type[typ] = by_type.get(typ, 0.0) + val
        if pid in pids:
            mine += val
    return (max(by_type.values()) if by_type else 0.0), by_type, mine


if __name__ == "__main__":
    p = GpuProbe()
    time.sleep(1)
    for _ in range(3):
        s = p.sample()
        total, by_type, _ = summarize(s)
        print(
            f"instances={len(s)} gpu(max engine type)={total:.1f}%  by type={ {k: round(v, 1) for k, v in by_type.items() if v > 0.05} }"
        )
        time.sleep(1)
