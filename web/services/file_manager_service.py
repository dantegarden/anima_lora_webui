"""File manager helpers for browsing whitelisted filesystem roots."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import tarfile
from typing import Any
import uuid
import zipfile

from web.services import settings_service


@dataclass(frozen=True)
class _ArchiveTarget:
    member_name: str
    target: Path
    is_dir: bool
    open_reader: Callable[[], Any] | None = None


def resolve_home_root() -> Path:
    return Path("/home").resolve()


def list_roots() -> dict[str, Any]:
    roots = []
    for root_id, label, path in _allowed_roots():
        roots.append({
            "id": root_id,
            "label": label,
            "path": _display_path(path),
        })
    return {
        "ok": True,
        "roots": roots,
    }


def list_directory(root_id: str, raw_path: str | None = None) -> dict[str, Any]:
    root = _resolve_root(root_id)
    target = _resolve_managed_path(root_id, raw_path)
    if not target.exists():
        raise FileNotFoundError("目录不存在")
    if not target.is_dir():
        raise ValueError("目标路径不是目录")

    entries = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        stat = entry.lstat()
        is_symlink = entry.is_symlink()
        entries.append({
            "name": entry.name,
            "path": _display_path(entry.resolve()) if not is_symlink else _display_path(entry),
            "kind": "dir" if entry.is_dir() else "file",
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "ext": entry.suffix.lower(),
            "is_symlink": is_symlink,
        })
    return {
        "ok": True,
        "root": {
            "id": root_id,
            "label": _root_label(root_id),
            "path": _display_path(root),
        },
        "directory": _display_path(target),
        "entries": entries,
    }


def resolve_download_file(root_id: str, raw_path: str) -> Path:
    target = _resolve_managed_path(root_id, raw_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("文件不存在")
    return target


def plan_extract_archive(
    root_id: str,
    raw_archive_path: str,
    raw_target_dir: str,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    root = _resolve_root(root_id)
    archive_path, archive_kind = _resolve_archive_file(root_id, raw_archive_path)
    target_dir = _resolve_managed_path(root_id, raw_target_dir)
    if not target_dir.exists():
        raise FileNotFoundError("目标目录不存在")
    if not target_dir.is_dir():
        raise ValueError("目标路径不是目录")

    file_count = 0
    dir_count = 0
    conflicts: list[dict[str, str]] = []
    for member in _iter_safe_archive_targets(root, archive_path, target_dir, archive_kind=archive_kind):
        if member.is_dir:
            dir_count += 1
        else:
            file_count += 1
            if member.target.exists():
                conflicts.append({
                    "member": member.member_name,
                    "target": _display_path(member.target),
                })

    return {
        "ok": True,
        "archive": {
            "name": archive_path.name,
            "path": _display_path(archive_path),
            "kind": archive_kind,
        },
        "target_dir": _display_path(target_dir),
        "summary": {
            "files": file_count,
            "dirs": dir_count,
            "conflicts": len(conflicts),
        },
        "conflicts": conflicts[:50],
        "can_extract": overwrite or not conflicts,
        "overwrite": overwrite,
    }


def start_extract_job(
    app: dict[str, Any],
    root_id: str,
    raw_archive_path: str,
    raw_target_dir: str,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    plan = plan_extract_archive(
        root_id,
        raw_archive_path,
        raw_target_dir,
        overwrite=overwrite,
    )
    if not overwrite and plan["summary"]["conflicts"]:
        raise ValueError("解压目标存在同名冲突，请先确认覆盖")

    store = _job_store(app)
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "extract",
        "state": "queued",
        "archive_path": plan["archive"]["path"],
        "archive_kind": plan["archive"]["kind"],
        "target_dir": plan["target_dir"],
        "overwrite": overwrite,
        "current": 0,
        "total": plan["summary"]["files"],
        "message": "等待解压",
        "error": "",
    }
    store[job_id] = job
    task = asyncio.create_task(_run_extract_job(
        job,
        root_id=root_id,
        raw_archive_path=raw_archive_path,
        raw_target_dir=raw_target_dir,
        overwrite=overwrite,
    ))
    app.setdefault("file_manager_job_tasks", {})[job_id] = task
    return {"ok": True, "job": dict(job)}


def get_job_status(app: dict[str, Any], job_id: str) -> dict[str, Any]:
    store = _job_store(app)
    job = store.get(job_id)
    if not job:
        raise FileNotFoundError("任务不存在")
    return {"ok": True, "job": dict(job)}


def rename_entry(root_id: str, raw_path: str, new_name: str) -> dict[str, Any]:
    source = _resolve_managed_path(root_id, raw_path)
    if not source.exists():
        raise FileNotFoundError("重命名目标不存在")
    if source.is_symlink():
        raise ValueError("不允许操作符号链接")

    name = str(new_name or "").strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("新名称不合法")

    target = source.parent / name
    if target == source:
        return {
            "ok": True,
            "renamed": {
                "name": source.name,
                "old_path": _display_path(source),
                "new_path": _display_path(source),
            },
        }
    if target.exists():
        raise FileExistsError("同名文件或目录已存在")

    source.rename(target)
    return {
        "ok": True,
        "renamed": {
            "name": target.name,
            "old_path": _display_path(source.parent / source.name),
            "new_path": _display_path(target),
        },
    }


def delete_entry(root_id: str, raw_path: str) -> dict[str, Any]:
    root = _resolve_root(root_id)
    target = _resolve_managed_path(root_id, raw_path)
    if not target.exists():
        raise FileNotFoundError("删除目标不存在")
    if target == root:
        raise ValueError("不允许删除管理根目录")
    if target.is_symlink():
        raise ValueError("不允许操作符号链接")

    kind = "dir" if target.is_dir() else "file"
    deleted_path = _display_path(target)
    if kind == "dir":
        shutil.rmtree(target)
    else:
        target.unlink()

    return {
        "ok": True,
        "deleted": {
            "path": deleted_path,
            "kind": kind,
            "name": target.name,
        },
    }


async def save_uploaded_file(root_id: str, raw_target_dir: str, field: Any) -> dict[str, Any]:
    filename = str(getattr(field, "filename", "") or "").strip()
    if not filename:
        raise ValueError("上传文件缺少文件名")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ValueError("上传文件名不合法")

    target_dir = _resolve_managed_path(root_id, raw_target_dir)
    if not target_dir.exists():
        raise FileNotFoundError("目标目录不存在")
    if not target_dir.is_dir():
        raise ValueError("目标路径不是目录")

    final_path = target_dir / filename
    overwritten = final_path.exists()
    temp_path = target_dir / f".{filename}.part"
    if temp_path.exists():
        temp_path.unlink()

    size = 0
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await field.read_chunk(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                size += len(chunk)
        temp_path.replace(final_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return {
        "ok": True,
        "uploaded": {
            "name": final_path.name,
            "path": _display_path(final_path),
            "size": size,
            "overwritten": overwritten,
        },
    }


async def _run_extract_job(
    job: dict[str, Any],
    *,
    root_id: str,
    raw_archive_path: str,
    raw_target_dir: str,
    overwrite: bool,
) -> None:
    root = _resolve_root(root_id)
    archive_path, archive_kind = _resolve_archive_file(root_id, raw_archive_path)
    target_dir = _resolve_managed_path(root_id, raw_target_dir)
    job["state"] = "running"
    job["message"] = "正在解压"
    try:
        for member in _iter_safe_archive_targets(
            root,
            archive_path,
            target_dir,
            archive_kind=archive_kind,
        ):
            if member.is_dir:
                member.target.mkdir(parents=True, exist_ok=True)
                continue
            member.target.parent.mkdir(parents=True, exist_ok=True)
            if member.target.exists() and not overwrite:
                raise ValueError(f"解压目标存在同名文件: {member.member_name}")
            if member.open_reader is None:
                raise ValueError(f"无法读取归档成员: {member.member_name}")
            source = member.open_reader()
            if source is None:
                raise ValueError(f"无法读取归档成员: {member.member_name}")
            with source, member.target.open("wb") as handle:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            job["current"] += 1
            job["message"] = f"已解压 {member.member_name}"
            await asyncio.sleep(0)
        job["state"] = "done"
        job["message"] = "解压完成"
    except Exception as exc:
        job["state"] = "error"
        job["error"] = str(exc)
        job["message"] = "解压失败"


def _allowed_roots() -> list[tuple[str, str, Path]]:
    return [
        ("home", "/home", resolve_home_root()),
        ("training_output", "训练输出", settings_service.resolve_output_root()),
    ]


def _resolve_root(root_id: str) -> Path:
    for current_id, _label, path in _allowed_roots():
        if current_id == root_id:
            return path.resolve()
    raise ValueError("未知的根目录")


def _root_label(root_id: str) -> str:
    for current_id, label, _path in _allowed_roots():
        if current_id == root_id:
            return label
    raise ValueError("未知的根目录")


def _resolve_managed_path(root_id: str, raw_path: str | None) -> Path:
    root = _resolve_root(root_id)
    clean = str(raw_path or "").strip()
    if not clean:
        candidate_raw = root
    else:
        incoming = Path(clean)
        if incoming.is_absolute():
            candidate_raw = incoming
        else:
            if ".." in incoming.parts:
                raise ValueError("路径不能包含 ..")
            candidate_raw = root / incoming
    candidate = candidate_raw.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("路径必须位于允许根目录内") from exc
    _reject_symlink_access(root, candidate_raw)
    return candidate


def _resolve_archive_file(root_id: str, raw_path: str) -> tuple[Path, str]:
    target = _resolve_managed_path(root_id, raw_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("归档文件不存在")
    archive_kind = _detect_archive_kind(target)
    if archive_kind is None:
        raise ValueError("只支持 tar/tar.gz/tgz/zip 归档")
    return target, archive_kind


def _detect_archive_kind(path: Path) -> str | None:
    name = path.name.lower()
    if name.endswith(".tar") or name.endswith(".tar.gz") or name.endswith(".tgz"):
        return "tar"
    if name.endswith(".zip"):
        return "zip"
    return None


def _iter_safe_archive_targets(
    root: Path,
    archive_path: Path,
    target_dir: Path,
    *,
    archive_kind: str,
):
    if archive_kind == "tar":
        with tarfile.open(archive_path, "r:*") as opened:
            for member in opened.getmembers():
                target = _resolve_archive_member_target(root, target_dir, member.name)
                if member.issym() or member.islnk():
                    raise ValueError(f"归档成员不支持符号链接: {member.name}")
                if member.isdir():
                    yield _ArchiveTarget(member_name=member.name, target=target, is_dir=True)
                    continue
                if not member.isfile():
                    raise ValueError(f"归档成员类型不支持: {member.name}")
                yield _ArchiveTarget(
                    member_name=member.name,
                    target=target,
                    is_dir=False,
                    open_reader=lambda current=member: opened.extractfile(current),
                )
        return
    if archive_kind == "zip":
        with zipfile.ZipFile(archive_path, "r") as opened:
            for member in opened.infolist():
                target = _resolve_archive_member_target(root, target_dir, member.filename)
                if _zip_info_is_symlink(member):
                    raise ValueError(f"归档成员不支持符号链接: {member.filename}")
                if member.is_dir():
                    yield _ArchiveTarget(member_name=member.filename, target=target, is_dir=True)
                    continue
                yield _ArchiveTarget(
                    member_name=member.filename,
                    target=target,
                    is_dir=False,
                    open_reader=lambda current=member: opened.open(current, "r"),
                )
        return
    raise ValueError("不支持的归档类型")


def _resolve_archive_member_target(root: Path, target_dir: Path, member_name: str) -> Path:
    normalized_name = str(member_name or "").replace("\\", "/")
    path = PurePosixPath(normalized_name)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts or path.is_absolute() or ".." in parts:
        raise ValueError(f"归档成员路径不合法: {member_name}")
    target = (target_dir / Path(*parts)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"归档成员越界: {member_name}") from exc
    _reject_symlink_access(root, target)
    return target


def _zip_info_is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0o170000
    return mode == 0o120000


def _job_store(app: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return app.setdefault("file_manager_jobs", {})


def _reject_symlink_access(root: Path, candidate_raw: Path) -> None:
    try:
        rel = candidate_raw.relative_to(root)
    except ValueError:
        rel = candidate_raw.resolve(strict=False).relative_to(root)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("不允许访问符号链接")
        if not current.exists():
            break


def _display_path(path: Path) -> str:
    return path.resolve().as_posix()
