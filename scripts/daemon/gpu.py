"""Best-effort GPU-occupancy probe for the serial dequeue guard.

Single GPU, one job at a time → between jobs exactly zero training procs
should hold VRAM. Before launching the next job the manager asks who's holding
the GPU so it can distinguish "free, go" from "a known dead job leaked VRAM,
reap it" from "an unknown proc is using the card, don't blind-kill it".

pynvml first (no subprocess, exact), ``nvidia-smi`` / ``mx-smi`` fallback, then
the PyTorch accelerator runtime, then give up gracefully — the guard degrades to
"assume free" rather than deadlocking the queue if neither is available (e.g.
CPU-only CI).
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from library.runtime.proc import no_window_kwargs


def gpu_pids() -> Optional[set[int]]:
    """PIDs with a **compute** context on any visible GPU.

    ``None`` means "couldn't tell" (no NVML, no nvidia-smi) — distinct from an
    empty set, which means "queried successfully, no compute job is running".

    Compute-only on purpose: the guard exists to spot leftover *training*
    procs, which use CUDA compute contexts. Graphics contexts (the Windows
    desktop compositor, browsers, any GPU-accelerated app) must NOT count, or
    on WDDM the guard would see a dozen innocent renderers every time and stall
    the queue for its full retry budget before launching anyway.
    """
    pids = _gpu_pids_nvml()
    if pids is not None:
        return pids
    return _gpu_pids_smi()


def gpu_mem() -> Optional[tuple[int, int]]:
    """``(used_mib, total_mib)`` summed over visible GPUs, or ``None``.

    The reliable busy/free signal on Windows WDDM, where per-process compute
    enumeration is meaningless (see ``gpu_pids``) but aggregate memory is still
    accurate. A real training run holds GBs; an idle desktop holds a few hundred
    MiB — so a fraction-of-total threshold cleanly tells the two apart.
    """
    mem = _gpu_mem_nvml()
    if mem is not None:
        return mem
    mem = _gpu_mem_smi()
    if mem is not None:
        return mem
    return _gpu_mem_torch()


def _gpu_mem_nvml() -> Optional[tuple[int, int]]:
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
    except Exception:
        return None
    try:
        used = total = 0
        for i in range(pynvml.nvmlDeviceGetCount()):
            info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(i))
            used += int(info.used)
            total += int(info.total)
        return (used // (1024 * 1024), total // (1024 * 1024))
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def _gpu_mem_smi() -> Optional[tuple[int, int]]:
    for name in ("nvidia-smi", "mx-smi"):
        smi = shutil.which(name)
        if smi is None:
            continue
        try:
            out = subprocess.run(
                [
                    smi,
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode != 0:
            continue
        used = total = 0
        for line in out.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                used += int(parts[0])
                total += int(parts[1])
        if total > 0:
            return (used, total)
    return None


def _gpu_mem_torch() -> Optional[tuple[int, int]]:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        used = total = 0
        for index in range(torch.cuda.device_count()):
            free_bytes, total_bytes = torch.cuda.mem_get_info(index)
            used += int(total_bytes - free_bytes)
            total += int(total_bytes)
        return (used // (1024 * 1024), total // (1024 * 1024)) if total > 0 else None
    except Exception:
        return None


def _gpu_pids_nvml() -> Optional[set[int]]:
    try:
        import pynvml  # type: ignore
    except Exception:
        return None
    try:
        pynvml.nvmlInit()
    except Exception:
        return None
    try:
        out: set[int] = set()
        for i in range(pynvml.nvmlDeviceGetCount()):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            # Compute contexts only — graphics processes (desktop, browser, …)
            # are not training jobs and must not gate the queue. Mirrors the
            # nvidia-smi fallback's --query-compute-apps.
            try:
                for proc in pynvml.nvmlDeviceGetComputeRunningProcesses(h):
                    out.add(int(proc.pid))
            except Exception:
                continue
        return out
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def _gpu_pids_smi() -> Optional[set[int]]:
    for name in ("nvidia-smi", "mx-smi"):
        smi = shutil.which(name)
        if smi is None:
            continue
        try:
            out = subprocess.run(
                [
                    smi,
                    "--query-compute-apps=pid",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode != 0:
            continue
        pids: set[int] = set()
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
        return pids
    return None
