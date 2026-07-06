"""Process-metric calculators (CPU / IO) for Kometa & ImageMaid subprocesses.

Split out of ``modules.process_control`` -- this cluster owns the
"how busy is the Kometa subprocess right now?" logic used by the
runtime status API and the maintenance-guard loop.

## What lives here

* ``calculate_process_cpu_percent(proc)`` -- returns 0-100+ CPU% for
  a psutil.Process and all its children, computed as a delta over
  the previous call.  First call for a given PID returns ``None``
  because there's no baseline yet.
* ``calculate_system_cpu_percent()`` -- returns 0-100 system-wide
  CPU% as a delta over the previous call.
* ``calculate_process_io_stats(proc, cache_name)`` -- returns a dict
  with cumulative and per-second disk read/write for a process tree.
* ``clear_process_metric_cache(pid, cache_name=None)`` -- drops
  cached counters for a PID (called after a process ends).

## Module-level caches

Three per-module dicts hold the previous-sample state so deltas can
be computed on the next call:

* ``KOMETA_CPU_CACHE`` -- PID -> {"time": t, "cpu": total_cpu_secs}
* ``SYSTEM_CPU_CACHE`` -- {"total": t, "idle": i} (global, single entry)
* ``PROCESS_IO_CACHE`` -- {"kometa": {pid -> ...}, "imagemaid": {pid -> ...}}

These are internal state; nothing outside this module references them
directly (verified by grep across the codebase during extraction).

## Backward compatibility

``modules.process_control`` re-exports every public name so callers
in ``quickstart.py`` (which imports via alias, e.g.
``calculate_process_cpu_percent as _calculate_process_cpu_percent``)
keep working unchanged.  6 test-suite monkeypatches that target
``qs_module._calculate_process_cpu_percent`` etc. also stay valid
because they mutate ``quickstart.__dict__``, not this module.
"""

from __future__ import annotations

import time

import psutil

KOMETA_CPU_CACHE: dict = {}
SYSTEM_CPU_CACHE: dict = {"total": None, "idle": None}
PROCESS_IO_CACHE: dict = {"kometa": {}, "imagemaid": {}}


def calculate_process_cpu_percent(proc):
    try:
        cpu_times = proc.cpu_times()
    except Exception:
        return None
    total_cpu = cpu_times.user + cpu_times.system
    try:
        for child in proc.children(recursive=True):
            try:
                child_times = child.cpu_times()
                total_cpu += child_times.user + child_times.system
            except Exception:
                continue
    except Exception:
        pass
    now = time.time()
    entry = KOMETA_CPU_CACHE.get(proc.pid)
    KOMETA_CPU_CACHE[proc.pid] = {"time": now, "cpu": total_cpu}
    if not entry:
        return None
    elapsed = now - entry.get("time", now)
    if elapsed <= 0:
        return None
    delta_cpu = total_cpu - entry.get("cpu", total_cpu)
    if delta_cpu < 0:
        return None
    percent = (delta_cpu / elapsed) * 100.0
    return max(0.0, percent)


def calculate_system_cpu_percent():
    try:
        cpu_times = psutil.cpu_times()
    except Exception:
        return None
    total = sum(cpu_times)
    idle = getattr(cpu_times, "idle", 0)
    last_total = SYSTEM_CPU_CACHE.get("total")
    last_idle = SYSTEM_CPU_CACHE.get("idle")
    SYSTEM_CPU_CACHE["total"] = total
    SYSTEM_CPU_CACHE["idle"] = idle
    if last_total is None or last_idle is None:
        return None
    delta_total = total - last_total
    if delta_total <= 0:
        return None
    delta_idle = idle - last_idle
    busy = max(0.0, delta_total - delta_idle)
    percent = (busy / delta_total) * 100.0
    return max(0.0, min(100.0, percent))


def calculate_process_io_stats(proc, cache_name):
    bucket = PROCESS_IO_CACHE.setdefault(cache_name, {})
    total_read = 0
    total_write = 0
    saw_counters = False

    def _accumulate_io(target_proc):
        nonlocal total_read, total_write, saw_counters
        try:
            counters = target_proc.io_counters()
        except Exception:
            return
        read_bytes = getattr(counters, "read_bytes", None)
        write_bytes = getattr(counters, "write_bytes", None)
        if read_bytes is None or write_bytes is None:
            return
        saw_counters = True
        total_read += max(0, int(read_bytes))
        total_write += max(0, int(write_bytes))

    _accumulate_io(proc)
    try:
        for child in proc.children(recursive=True):
            _accumulate_io(child)
    except Exception:
        pass

    if not saw_counters:
        return None

    now = time.time()
    entry = bucket.get(proc.pid)
    bucket[proc.pid] = {"time": now, "read": total_read, "write": total_write}

    read_rate_mb_s = None
    write_rate_mb_s = None
    if entry:
        elapsed = now - entry.get("time", now)
        if elapsed > 0:
            delta_read = total_read - entry.get("read", total_read)
            delta_write = total_write - entry.get("write", total_write)
            if delta_read >= 0:
                read_rate_mb_s = delta_read / (1024 * 1024) / elapsed
            if delta_write >= 0:
                write_rate_mb_s = delta_write / (1024 * 1024) / elapsed

    return {
        "disk_read_mb": total_read / (1024 * 1024),
        "disk_write_mb": total_write / (1024 * 1024),
        "disk_read_rate_mb_s": read_rate_mb_s,
        "disk_write_rate_mb_s": write_rate_mb_s,
    }


def clear_process_metric_cache(pid, cache_name=None):
    if pid is None:
        return
    KOMETA_CPU_CACHE.pop(pid, None)
    if cache_name:
        PROCESS_IO_CACHE.setdefault(cache_name, {}).pop(pid, None)
