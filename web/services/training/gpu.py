"""GPU selection and SMI parsing helpers for WebUI training.

The NVIDIA path keeps using ``nvidia-smi``.  MetaX/MACA hosts expose
``mx-smi`` instead, so both commands are probed before falling back to the
PyTorch runtime (which knows how to enumerate the active accelerator backend).
MetaX images ship ``ht-smi`` whose CLI is not nvidia-smi compatible; the
PyTorch fallback is the reliable path there.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


CreateSubprocessExec = Callable[..., Awaitable[Any]]
SMI_COMMANDS = ("nvidia-smi", "mx-smi")


async def get_gpu_stats(
    gpu_whitelist: list[int] | None = None,
    *,
    create_subprocess_exec: CreateSubprocessExec | None = None,
    stdout_pipe: Any | None = None,
    stderr_devnull: Any | None = None,
) -> dict[str, Any]:
    runner = create_subprocess_exec or asyncio.create_subprocess_exec
    for smi in SMI_COMMANDS:
        text = await _run_smi(
            runner,
            smi,
            (
                "--query-gpu=index,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ),
            stdout_pipe=stdout_pipe,
            stderr_devnull=stderr_devnull,
        )
        if text is None:
            continue
        rows = parse_gpu_stats_rows(text)
        if rows:
            return _select_gpu_stats(rows, gpu_whitelist)

    return await asyncio.to_thread(_get_gpu_stats_torch, gpu_whitelist)


def _select_gpu_stats(rows: list[dict[str, int]], gpu_whitelist: list[int] | None) -> dict[str, Any]:
    selected = normalize_gpu_whitelist(gpu_whitelist)
    if selected:
        selected_set = set(selected)
        rows = [row for row in rows if row["index"] in selected_set]
    else:
        rows = rows[:1]
    return aggregate_gpu_stats_rows(rows)


async def _run_smi(
    runner: CreateSubprocessExec,
    executable: str,
    args: tuple[str, ...],
    *,
    stdout_pipe: Any | None,
    stderr_devnull: Any | None,
) -> str | None:
    try:
        proc = await runner(
            executable,
            *args,
            stdout=stdout_pipe if stdout_pipe is not None else asyncio.subprocess.PIPE,
            stderr=stderr_devnull if stderr_devnull is not None else asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
    except Exception:
        return None
    returncode = getattr(proc, "returncode", 0)
    if returncode not in (0, None):
        return None
    return stdout.decode(errors="replace")


def parse_gpu_stats_rows(text: str) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            rows.append({
                "index": int(parts[0]),
                "memory_used_mb": int(parts[1]),
                "memory_total_mb": int(parts[2]),
                "gpu_util": int(parts[3]),
                "gpu_temp": int(parts[4]),
            })
        except ValueError:
            continue
    return rows


def aggregate_gpu_stats_rows(rows: list[dict[str, int]]) -> dict[str, Any]:
    if not rows:
        return {}
    indices = [row["index"] for row in rows]
    used_mb = sum(row["memory_used_mb"] for row in rows)
    total_mb = sum(row["memory_total_mb"] for row in rows)
    return {
        "gpu_index": indices[0],
        "gpu_indices": indices,
        "vram_used_gb": round(used_mb / 1024, 2),
        "vram_total_gb": round(total_mb / 1024, 2),
        "gpu_util": max(row["gpu_util"] for row in rows),
        "gpu_temp": max(row["gpu_temp"] for row in rows),
    }


async def list_available_gpus(
    *,
    create_subprocess_exec: CreateSubprocessExec | None = None,
    stdout_pipe: Any | None = None,
    stderr_devnull: Any | None = None,
) -> list[dict[str, Any]]:
    runner = create_subprocess_exec or asyncio.create_subprocess_exec
    for smi in SMI_COMMANDS:
        text = await _run_smi(
            runner,
            smi,
            ("--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"),
            stdout_pipe=stdout_pipe,
            stderr_devnull=stderr_devnull,
        )
        if text is None:
            continue
        gpus: list[dict[str, Any]] = []
        for line in text.splitlines():
            item = parse_available_gpu_row(line)
            if item is not None:
                gpus.append(item)
        if gpus:
            return gpus

    return await asyncio.to_thread(_list_available_gpus_torch)


def _list_available_gpus_torch() -> list[dict[str, Any]]:
    try:
        import torch

        if not torch.cuda.is_available():
            return []
        gpus: list[dict[str, Any]] = []
        for index in range(torch.cuda.device_count()):
            name = torch.cuda.get_device_name(index)
            total_mb = int(torch.cuda.get_device_properties(index).total_memory // (1024 * 1024))
            gpus.append(
                {
                    "index": index,
                    "name": name,
                    "label": f"GPU {index} · {name}",
                    "memory_total_mb": total_mb,
                    "memory_total_gb": round(total_mb / 1024, 1),
                }
            )
        return gpus
    except Exception:
        return []


def _get_gpu_stats_torch(gpu_whitelist: list[int] | None = None) -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {}
        count = torch.cuda.device_count()
        selected = normalize_gpu_whitelist(gpu_whitelist) or [0]
        selected = [index for index in selected if 0 <= index < count]
        if not selected:
            return {}
        rows: list[dict[str, int]] = []
        for index in selected:
            free_bytes, total_bytes = torch.cuda.mem_get_info(index)
            used_mb = int((total_bytes - free_bytes) // (1024 * 1024))
            total_mb = int(total_bytes // (1024 * 1024))
            utilization = 0
            try:
                utilization = int(torch.cuda.utilization(index))
            except Exception:
                pass
            rows.append(
                {
                    "index": index,
                    "memory_used_mb": used_mb,
                    "memory_total_mb": total_mb,
                    "gpu_util": utilization,
                    "gpu_temp": 0,
                }
            )
        return aggregate_gpu_stats_rows(rows)
    except Exception:
        return {}


def parse_available_gpu_row(line: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.split(",", 2)]
    if len(parts) < 2:
        return None
    try:
        index = int(parts[0])
    except ValueError:
        return None
    memory_total_mb = int_or_none(parts[2]) if len(parts) >= 3 else None
    item: dict[str, Any] = {
        "index": index,
        "name": parts[1],
        "label": f"GPU {index} · {parts[1]}",
    }
    if memory_total_mb is not None:
        item["memory_total_mb"] = memory_total_mb
        item["memory_total_gb"] = round(memory_total_mb / 1024, 1)
    return item


def normalize_gpu_whitelist(value: Any) -> list[int]:
    if value is None or value == "":
        return []
    raw_items = value if isinstance(value, list) else [value]
    out: list[int] = []
    for item in raw_items:
        try:
            index = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if index < 0 or index in out:
            continue
        out.append(index)
    return out


def apply_gpu_whitelist(env: dict[str, str], whitelist: list[int]) -> None:
    if whitelist:
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(index) for index in whitelist)
        # MetaX runtimes accept the CUDA-compatible variable above; mirror it
        # for tooling that looks for the MACA-native spelling.
        env["MACA_VISIBLE_DEVICES"] = env["CUDA_VISIBLE_DEVICES"]


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
