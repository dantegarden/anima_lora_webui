"""File manager browsing and download routes."""

from __future__ import annotations

from urllib.parse import quote

from aiohttp import web

from web.services.file_manager_service import (
    get_job_status,
    list_directory,
    list_roots,
    plan_extract_archive,
    rename_entry,
    resolve_download_file,
    save_uploaded_file,
    start_extract_job,
)


def setup_file_manager_routes(app: web.Application) -> None:
    app.router.add_get("/api/file-manager/roots", handle_file_manager_roots)
    app.router.add_get("/api/file-manager/list", handle_file_manager_list)
    app.router.add_get("/api/file-manager/download", handle_file_manager_download)
    app.router.add_post("/api/file-manager/upload", handle_file_manager_upload)
    app.router.add_post("/api/file-manager/extract/plan", handle_file_manager_extract_plan)
    app.router.add_post("/api/file-manager/extract/run", handle_file_manager_extract_run)
    app.router.add_get("/api/file-manager/jobs/{job_id}", handle_file_manager_job_status)
    app.router.add_post("/api/file-manager/rename", handle_file_manager_rename)


async def handle_file_manager_roots(request: web.Request) -> web.Response:
    return web.json_response(list_roots())


async def handle_file_manager_list(request: web.Request) -> web.Response:
    root = str(request.query.get("root") or "").strip()
    if not root:
        return web.json_response({"ok": False, "error": "缺少 root 参数"}, status=400)
    raw_path = str(request.query.get("path") or "").strip()
    try:
        return web.json_response(list_directory(root, raw_path))
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)


async def handle_file_manager_download(request: web.Request) -> web.StreamResponse:
    root = str(request.query.get("root") or "").strip()
    if not root:
        return web.json_response({"ok": False, "error": "缺少 root 参数"}, status=400)
    raw_path = str(request.query.get("path") or "").strip()
    if not raw_path:
        return web.json_response({"ok": False, "error": "缺少 path 参数"}, status=400)
    try:
        path = resolve_download_file(root, raw_path)
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}",
    }
    return web.FileResponse(path, headers=headers)


async def handle_file_manager_upload(request: web.Request) -> web.Response:
    reader = await request.multipart()
    root = ""
    target_path = ""
    upload_field = None

    while True:
        field = await reader.next()
        if field is None:
            break
        if field.name == "root":
            root = (await field.text()).strip()
        elif field.name == "target_path":
            target_path = (await field.text()).strip()
        elif field.name == "file":
            upload_field = field

    if not root:
        return web.json_response({"ok": False, "error": "缺少 root 参数"}, status=400)
    if not target_path:
        return web.json_response({"ok": False, "error": "缺少 target_path 参数"}, status=400)
    if upload_field is None:
        return web.json_response({"ok": False, "error": "缺少 file 参数"}, status=400)

    try:
        payload = await save_uploaded_file(root, target_path, upload_field)
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    return web.json_response(payload)


async def handle_file_manager_extract_plan(request: web.Request) -> web.Response:
    data = await request.json()
    root = str(data.get("root") or "").strip()
    archive_path = str(data.get("archive_path") or "").strip()
    target_dir = str(data.get("target_dir") or "").strip()
    overwrite = bool(data.get("overwrite"))
    if not root or not archive_path or not target_dir:
        return web.json_response({"ok": False, "error": "缺少解压参数"}, status=400)
    try:
        payload = plan_extract_archive(root, archive_path, target_dir, overwrite=overwrite)
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    return web.json_response(payload)


async def handle_file_manager_extract_run(request: web.Request) -> web.Response:
    data = await request.json()
    root = str(data.get("root") or "").strip()
    archive_path = str(data.get("archive_path") or "").strip()
    target_dir = str(data.get("target_dir") or "").strip()
    overwrite = bool(data.get("overwrite"))
    if not root or not archive_path or not target_dir:
        return web.json_response({"ok": False, "error": "缺少解压参数"}, status=400)
    try:
        payload = start_extract_job(
            request.app,
            root,
            archive_path,
            target_dir,
            overwrite=overwrite,
        )
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    return web.json_response(payload)


async def handle_file_manager_job_status(request: web.Request, job_id: str) -> web.Response:
    try:
        payload = get_job_status(request.app, job_id)
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    return web.json_response(payload)


async def handle_file_manager_rename(request: web.Request) -> web.Response:
    data = await request.json()
    root = str(data.get("root") or "").strip()
    raw_path = str(data.get("path") or "").strip()
    new_name = str(data.get("new_name") or "").strip()
    if not root or not raw_path or not new_name:
        return web.json_response({"ok": False, "error": "缺少重命名参数"}, status=400)
    try:
        payload = rename_entry(root, raw_path, new_name)
    except FileNotFoundError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except FileExistsError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=409)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    return web.json_response(payload)
