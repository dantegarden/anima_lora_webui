from __future__ import annotations

import asyncio
import importlib.util
import io
from pathlib import Path
import zipfile

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from web.services import file_manager_service


def _load_routes_module():
    path = Path(__file__).resolve().parents[1] / "web" / "routes" / "file_manager.py"
    spec = importlib.util.spec_from_file_location("test_file_manager_routes_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


file_manager_routes = _load_routes_module()


class _FakeRequest:
    def __init__(self, *, query=None, app=None):
        self.query = query or {}
        self.app = app or {}


class _FakeMultipartField:
    def __init__(self, name: str, value=None, *, filename: str | None = None):
        self.name = name
        self._value = value
        self.filename = filename

    async def text(self):
        return str(self._value or "")


class _FakeMultipartReader:
    def __init__(self, fields):
        self._fields = list(fields)

    async def next(self):
        if not self._fields:
            return None
        return self._fields.pop(0)


def _run(coro):
    return asyncio.run(coro)


def test_file_manager_roots_route_returns_whitelisted_roots(monkeypatch):
    monkeypatch.setattr(
        file_manager_routes,
        "list_roots",
        lambda: {
            "ok": True,
            "roots": [{"id": "home", "label": "/home", "path": "/home"}],
        },
    )

    response = _run(file_manager_routes.handle_file_manager_roots(_FakeRequest()))

    assert response.status == 200
    assert response.text == '{"ok": true, "roots": [{"id": "home", "label": "/home", "path": "/home"}]}'


def test_file_manager_list_route_maps_service_errors(monkeypatch):
    monkeypatch.setattr(
        file_manager_routes,
        "list_directory",
        lambda root, path: (_ for _ in ()).throw(ValueError("路径必须位于允许根目录内")),
    )

    response = _run(
        file_manager_routes.handle_file_manager_list(
            _FakeRequest(query={"root": "home", "path": "/tmp/outside"})
        )
    )

    assert response.status == 403
    assert response.text == '{"ok": false, "error": "\\u8def\\u5f84\\u5fc5\\u987b\\u4f4d\\u4e8e\\u5141\\u8bb8\\u6839\\u76ee\\u5f55\\u5185"}'


def test_file_manager_download_route_returns_attachment(monkeypatch, tmp_path):
    target = tmp_path / "demo.safetensors"
    target.write_bytes(b"ok")

    monkeypatch.setattr(file_manager_routes, "resolve_download_file", lambda root, path: target.resolve())

    response = _run(
        file_manager_routes.handle_file_manager_download(
            _FakeRequest(query={"root": "training_output", "path": str(target)})
        )
    )

    assert response.status == 200
    assert response._path == target.resolve()
    assert response.headers["Content-Disposition"].startswith("attachment;")


def test_file_manager_upload_route_uses_service_and_returns_payload(monkeypatch):
    fields = [
        _FakeMultipartField("root", "home"),
        _FakeMultipartField("target_path", "/home/datasets"),
        _FakeMultipartField("file", None, filename="dataset.tar"),
    ]
    request = _FakeRequest()

    async def multipart():
        return _FakeMultipartReader(fields)

    request.multipart = multipart

    async def fake_save_uploaded_file(root, target_path, field):
        assert root == "home"
        assert target_path == "/home/datasets"
        assert field.filename == "dataset.tar"
        return {"ok": True, "uploaded": {"name": "dataset.tar"}}

    monkeypatch.setattr(file_manager_routes, "save_uploaded_file", fake_save_uploaded_file)

    response = _run(file_manager_routes.handle_file_manager_upload(request))

    assert response.status == 200
    assert response.text == '{"ok": true, "uploaded": {"name": "dataset.tar"}}'


def test_file_manager_extract_plan_route_returns_conflict_summary(monkeypatch):
    class _JsonRequest(_FakeRequest):
        async def json(self):
            return {
                "root": "home",
                "archive_path": "/home/dataset.tar",
                "target_dir": "/home/data",
                "overwrite": False,
            }

    monkeypatch.setattr(
        file_manager_routes,
        "plan_extract_archive",
        lambda root, archive_path, target_dir, overwrite=False: {
            "ok": True,
            "summary": {"files": 2, "dirs": 1, "conflicts": 1},
            "conflicts": [{"member": "existing.txt", "target": "/home/data/existing.txt"}],
            "can_extract": False,
        },
    )

    response = _run(file_manager_routes.handle_file_manager_extract_plan(_JsonRequest()))

    assert response.status == 200
    assert '"can_extract": false' in response.text


def test_file_manager_extract_run_and_job_status_routes_use_job_store(monkeypatch):
    class _JsonRequest(_FakeRequest):
        async def json(self):
            return {
                "root": "home",
                "archive_path": "/home/dataset.tar",
                "target_dir": "/home/data",
                "overwrite": True,
            }

    app = {}
    monkeypatch.setattr(
        file_manager_routes,
        "start_extract_job",
        lambda app_obj, root, archive_path, target_dir, overwrite=False: {
            "ok": True,
            "job": {
                "id": "job-1",
                "state": "queued",
                "current": 0,
                "total": 2,
            },
        },
    )
    monkeypatch.setattr(
        file_manager_routes,
        "get_job_status",
        lambda app_obj, job_id: {
            "ok": True,
            "job": {
                "id": job_id,
                "state": "done",
                "current": 2,
                "total": 2,
            },
        },
    )

    start_response = _run(file_manager_routes.handle_file_manager_extract_run(_JsonRequest(app=app)))
    status_response = _run(
        file_manager_routes.handle_file_manager_job_status(
            _FakeRequest(app=app, query={}),
            job_id="job-1",
        )
    )

    assert start_response.status == 200
    assert '"id": "job-1"' in start_response.text
    assert status_response.status == 200
    assert '"state": "done"' in status_response.text


def test_file_manager_rename_route_returns_renamed_payload(monkeypatch):
    class _JsonRequest(_FakeRequest):
        async def json(self):
            return {
                "root": "home",
                "path": "/home/datasets/old-name.tar",
                "new_name": "new-name.tar",
            }

    monkeypatch.setattr(
        file_manager_routes,
        "rename_entry",
        lambda root, path, new_name: {
            "ok": True,
            "renamed": {
                "old_path": path,
                "new_path": f"/home/datasets/{new_name}",
            },
        },
    )

    response = _run(file_manager_routes.handle_file_manager_rename(_JsonRequest()))

    assert response.status == 200
    assert '"new_path": "/home/datasets/new-name.tar"' in response.text


def test_file_manager_delete_route_returns_deleted_payload(monkeypatch):
    class _JsonRequest(_FakeRequest):
        async def json(self):
            return {
                "root": "home",
                "path": "/home/datasets/old-dir",
            }

    monkeypatch.setattr(
        file_manager_routes,
        "delete_entry",
        lambda root, path: {
            "ok": True,
            "deleted": {
                "path": path,
                "kind": "dir",
            },
        },
    )

    response = _run(file_manager_routes.handle_file_manager_delete(_JsonRequest()))

    assert response.status == 200
    assert '"kind": "dir"' in response.text


def test_file_manager_delete_route_accepts_multiple_paths(monkeypatch):
    class _JsonRequest(_FakeRequest):
        async def json(self):
            return {
                "root": "home",
                "paths": ["/home/datasets/a.txt", "/home/datasets/nested"],
            }

    monkeypatch.setattr(
        file_manager_routes,
        "delete_entries",
        lambda root, paths: {
            "ok": True,
            "deleted_count": len(paths),
            "deleted": [{"path": path} for path in paths],
        },
    )

    response = _run(file_manager_routes.handle_file_manager_delete(_JsonRequest()))

    assert response.status == 200
    assert '"deleted_count": 2' in response.text


def test_file_manager_upload_route_keeps_binary_archive_bytes(tmp_path, monkeypatch):
    home_root = tmp_path / "home"
    target_dir = home_root / "datasets"
    home_root.mkdir(parents=True)
    target_dir.mkdir(parents=True)

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("sample.txt", "hello zip")
    archive_bytes = archive_buffer.getvalue()

    monkeypatch.setattr(file_manager_service, "resolve_home_root", lambda: home_root.resolve())
    monkeypatch.setattr(
        file_manager_service.settings_service,
        "resolve_output_root",
        lambda: (tmp_path / "output" / "runs").resolve(),
    )

    async def run_case():
        app = web.Application(client_max_size=16 * 1024 * 1024)
        file_manager_routes.setup_file_manager_routes(app)
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            form = FormData()
            form.add_field("root", "home")
            form.add_field("target_path", str(target_dir))
            form.add_field(
                "file",
                archive_bytes,
                filename="archive.zip",
                content_type="application/zip",
            )
            response = await client.post("/api/file-manager/upload", data=form)
            payload = await response.json()
            return response.status, payload
        finally:
            await client.close()

    status, payload = _run(run_case())

    saved_path = target_dir / "archive.zip"
    assert status == 200
    assert payload["ok"] is True
    assert saved_path.read_bytes() == archive_bytes


def test_file_manager_routes_are_registered_before_static_catchalls():
    source = Path(file_manager_routes.__file__).read_text(encoding="utf-8")

    assert '"/api/file-manager/roots"' in source
    assert '"/api/file-manager/list"' in source
    assert '"/api/file-manager/download"' in source
    assert '"/api/file-manager/upload"' in source
    assert '"/api/file-manager/extract/plan"' in source
    assert '"/api/file-manager/extract/run"' in source
    assert '"/api/file-manager/jobs/{job_id}"' in source
    assert '"/api/file-manager/rename"' in source
    assert '"/api/file-manager/delete"' in source
