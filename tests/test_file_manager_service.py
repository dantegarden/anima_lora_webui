from __future__ import annotations

from pathlib import Path
import asyncio
import tarfile
import io
import zipfile

import pytest

from web.services import file_manager_service


def test_file_manager_lists_roots_and_current_directory(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    training_root = tmp_path / "output" / "runs"
    dataset_dir = home_root / "datasets"
    archive_file = home_root / "archive.tar"
    dataset_dir.mkdir(parents=True)
    training_root.mkdir(parents=True)
    archive_file.write_bytes(b"tar")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: training_root.resolve(),
    )

    roots = file_manager_service.list_roots()

    assert roots["ok"] is True
    assert roots["roots"] == [
        {"id": "home", "label": "/home", "path": home_root.resolve().as_posix()},
        {"id": "training_output", "label": "训练输出", "path": training_root.resolve().as_posix()},
    ]

    listing = file_manager_service.list_directory("home", str(home_root))

    assert listing["ok"] is True
    assert listing["root"]["id"] == "home"
    assert listing["directory"] == home_root.resolve().as_posix()
    assert [item["name"] for item in listing["entries"]] == ["archive.tar", "datasets"]
    assert [item["kind"] for item in listing["entries"]] == ["file", "dir"]
    assert listing["entries"][0]["path"] == archive_file.resolve().as_posix()
    assert listing["entries"][1]["path"] == dataset_dir.resolve().as_posix()


def test_file_manager_resolve_download_file_stays_within_allowed_root(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    training_root = tmp_path / "output" / "runs"
    weight_path = training_root / "demo.safetensors"
    outside = tmp_path / "outside.safetensors"
    home_root.mkdir(parents=True)
    training_root.mkdir(parents=True)
    weight_path.write_bytes(b"ok")
    outside.write_bytes(b"bad")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: training_root.resolve(),
    )

    resolved = file_manager_service.resolve_download_file(
        "training_output",
        str(weight_path),
    )

    assert resolved == weight_path.resolve()

    with pytest.raises(ValueError, match="允许根目录"):
        file_manager_service.resolve_download_file("training_output", str(outside))


class _FakeUploadField:
    def __init__(self, *, filename: str, chunks: list[bytes]):
        self.filename = filename
        self._chunks = list(chunks)

    async def read_chunk(self, _size: int = 0) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_file_manager_save_upload_file_overwrites_existing_file(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    target_dir = home_root / "datasets"
    target_file = target_dir / "dataset.tar"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    target_file.write_bytes(b"old-content")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    result = asyncio.run(
        file_manager_service.save_uploaded_file(
            "home",
            str(target_dir),
            _FakeUploadField(filename="dataset.tar", chunks=[b"new-", b"content"]),
        )
    )

    assert result["ok"] is True
    assert result["uploaded"]["name"] == "dataset.tar"
    assert result["uploaded"]["path"] == target_file.resolve().as_posix()
    assert result["uploaded"]["size"] == len(b"new-content")
    assert result["uploaded"]["overwritten"] is True
    assert target_file.read_bytes() == b"new-content"


def test_file_manager_plan_extract_archive_reports_conflicts(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    archive_path = home_root / "dataset.tar"
    target_dir = home_root / "datasets"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    (target_dir / "existing.txt").write_text("old", encoding="utf-8")

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "existing.txt").write_text("new", encoding="utf-8")
    (source_dir / "fresh.txt").write_text("fresh", encoding="utf-8")
    with tarfile.open(archive_path, "w") as tar:
        tar.add(source_dir / "existing.txt", arcname="existing.txt")
        tar.add(source_dir / "fresh.txt", arcname="nested/fresh.txt")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    payload = file_manager_service.plan_extract_archive(
        "home",
        str(archive_path),
        str(target_dir),
        overwrite=False,
    )

    assert payload["ok"] is True
    assert payload["archive"]["name"] == "dataset.tar"
    assert payload["target_dir"] == target_dir.resolve().as_posix()
    assert payload["summary"]["files"] == 2
    assert payload["summary"]["conflicts"] == 1
    assert payload["conflicts"] == [
        {
            "member": "existing.txt",
            "target": (target_dir / "existing.txt").resolve().as_posix(),
        }
    ]
    assert payload["can_extract"] is False


def test_file_manager_extract_job_unpacks_tar_after_confirmation(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    archive_path = home_root / "dataset.tar"
    target_dir = home_root / "datasets"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha", encoding="utf-8")
    nested = source_dir / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("beta", encoding="utf-8")
    with tarfile.open(archive_path, "w") as tar:
        tar.add(source_dir / "a.txt", arcname="a.txt")
        tar.add(nested / "b.txt", arcname="nested/b.txt")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    async def run_case():
        app = {}
        started = file_manager_service.start_extract_job(
            app,
            "home",
            str(archive_path),
            str(target_dir),
            overwrite=False,
        )
        job_id = started["job"]["id"]
        for _ in range(20):
            status = file_manager_service.get_job_status(app, job_id)
            if status["job"]["state"] in {"done", "error"}:
                return status
            await asyncio.sleep(0.01)
        return file_manager_service.get_job_status(app, job_id)

    status = asyncio.run(run_case())

    assert status["job"]["state"] == "done"
    assert (target_dir / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (target_dir / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"
    assert status["job"]["current"] == 2
    assert status["job"]["total"] == 2


def test_file_manager_rename_entry_renames_file_in_same_directory(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    dataset_dir = home_root / "datasets"
    source = dataset_dir / "old-name.tar"
    home_root.mkdir(parents=True)
    dataset_dir.mkdir(parents=True)
    source.write_text("payload", encoding="utf-8")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    payload = file_manager_service.rename_entry("home", str(source), "new-name.tar")

    renamed = dataset_dir / "new-name.tar"
    assert payload["ok"] is True
    assert payload["renamed"]["old_path"] == source.resolve().as_posix()
    assert payload["renamed"]["new_path"] == renamed.resolve().as_posix()
    assert renamed.read_text(encoding="utf-8") == "payload"
    assert not source.exists()


def test_file_manager_rename_entry_rejects_conflicts_and_invalid_name(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    dataset_dir = home_root / "datasets"
    source = dataset_dir / "old-name.tar"
    conflict = dataset_dir / "exists.tar"
    home_root.mkdir(parents=True)
    dataset_dir.mkdir(parents=True)
    source.write_text("payload", encoding="utf-8")
    conflict.write_text("conflict", encoding="utf-8")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    with pytest.raises(FileExistsError, match="同名"):
        file_manager_service.rename_entry("home", str(source), "exists.tar")

    with pytest.raises(ValueError, match="名称不合法"):
        file_manager_service.rename_entry("home", str(source), "../escape.tar")


def test_file_manager_plan_extract_archive_supports_zip(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    archive_path = home_root / "dataset.zip"
    target_dir = home_root / "datasets"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("existing.txt", "new")
        zipped.writestr("nested/fresh.txt", "fresh")
    archive_path.write_bytes(buffer.getvalue())
    (target_dir / "existing.txt").write_text("old", encoding="utf-8")

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    payload = file_manager_service.plan_extract_archive(
        "home",
        str(archive_path),
        str(target_dir),
        overwrite=False,
    )

    assert payload["ok"] is True
    assert payload["archive"]["name"] == "dataset.zip"
    assert payload["summary"]["files"] == 2
    assert payload["summary"]["conflicts"] == 1


def test_file_manager_extract_job_unpacks_zip_after_confirmation(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    archive_path = home_root / "dataset.zip"
    target_dir = home_root / "datasets"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("a.txt", "alpha")
        zipped.writestr("nested/b.txt", "beta")
    archive_path.write_bytes(buffer.getvalue())

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    async def run_case():
        app = {}
        started = file_manager_service.start_extract_job(
            app,
            "home",
            str(archive_path),
            str(target_dir),
            overwrite=False,
        )
        job_id = started["job"]["id"]
        for _ in range(20):
            status = file_manager_service.get_job_status(app, job_id)
            if status["job"]["state"] in {"done", "error"}:
                return status
            await asyncio.sleep(0.01)
        return file_manager_service.get_job_status(app, job_id)

    status = asyncio.run(run_case())

    assert status["job"]["state"] == "done"
    assert (target_dir / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (target_dir / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"
