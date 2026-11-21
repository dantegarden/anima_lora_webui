import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"
CODE_SERVER_PATCH = ROOT / "docker" / "patch_code_server_extensions.js"


def test_root_password_default_is_owned_by_entrypoint_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "SSH_PASSWORD=" not in dockerfile
    assert 'SSH_PASSWORD="${SSH_PASSWORD:-bizyair}"' in entrypoint
    assert 'PASSWORD="$(openssl rand -hex 16)"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="CODE_SERVER_PASSWORD"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="PASSWORD"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="generated"' in entrypoint
    assert "CODE-SERVER LOGIN PASSWORD (%s): %s" in entrypoint
    assert 'CODE_SERVER_AUTH="${CODE_SERVER_AUTH:-password}"' in entrypoint
    assert 'CODE-SERVER AUTHENTICATION DISABLED' in entrypoint
    assert "expected password or none" in entrypoint
    assert entrypoint.count("print_code_server_auth") == 3
    assert "rm -f /root/.config/code-server/config.yaml" in entrypoint
    assert "MSgouUQP4vhET" not in dockerfile
    assert "MSgouUQP4vhET" not in entrypoint


def test_docker_image_installs_latest_code_server_and_runs_it_externally() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    supervisor = (ROOT / "docker" / "supervisord.conf").read_text(encoding="utf-8")

    assert "shellinabox" not in dockerfile.lower()
    assert "shellinabox" not in supervisor.lower()
    assert "https://code-server.dev/install.sh" in dockerfile
    assert "patch_code_server_extensions.js" in dockerfile
    assert "/usr/lib/code-server/lib/vscode/extensions" in dockerfile
    assert "CODE_SERVER_AUTH=password" in dockerfile
    assert "CODE_SERVER_PORT=4200" in dockerfile
    assert "[program:code-server]" in supervisor
    assert "--bind-addr 0.0.0.0:%(ENV_CODE_SERVER_PORT)s" in supervisor
    assert "--auth %(ENV_CODE_SERVER_AUTH)s" in supervisor


def test_code_server_patch_only_removes_missing_browser_bundles() -> None:
    patch = CODE_SERVER_PATCH.read_text(encoding="utf-8")

    assert 'typeof manifest.browser !== "string"' in patch
    assert '`${browserEntry}.js`' in patch
    assert "candidates.some" in patch
    assert "delete manifest.browser" in patch


def test_code_server_patch_preserves_existing_browser_bundles(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the code-server manifest patch")

    missing_dir = tmp_path / "missing-browser"
    present_dir = tmp_path / "present-browser"
    missing_dir.mkdir()
    (present_dir / "dist" / "browser").mkdir(parents=True)
    (missing_dir / "package.json").write_text(
        json.dumps({"name": "missing-browser", "main": "./dist/extension.js", "browser": "./dist/browser/extension.js"}),
        encoding="utf-8",
    )
    (present_dir / "package.json").write_text(
        json.dumps({"name": "present-browser", "browser": "./dist/browser/extension"}),
        encoding="utf-8",
    )
    (present_dir / "dist" / "browser" / "extension.js").write_text("", encoding="utf-8")

    subprocess.run([node, str(CODE_SERVER_PATCH), str(tmp_path)], check=True)

    missing_manifest = json.loads((missing_dir / "package.json").read_text(encoding="utf-8"))
    present_manifest = json.loads((present_dir / "package.json").read_text(encoding="utf-8"))
    assert "browser" not in missing_manifest
    assert present_manifest["browser"] == "./dist/browser/extension"


def test_docker_image_installs_ossutil_with_official_installer() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "https://gosspublic.alicdn.com/ossutil/install.sh" in dockerfile
    assert "ossutil --version" in dockerfile
