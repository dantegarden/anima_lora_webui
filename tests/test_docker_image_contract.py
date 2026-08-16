from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"


def test_root_password_default_is_owned_by_entrypoint_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "SSH_PASSWORD=" not in dockerfile
    assert 'SSH_PASSWORD="${SSH_PASSWORD:-bizyair}"' in entrypoint
    assert 'PASSWORD="$(openssl rand -hex 16)"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="CODE_SERVER_PASSWORD"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="PASSWORD"' in entrypoint
    assert 'CODE_SERVER_PASSWORD_SOURCE="generated"' in entrypoint
    assert "code-server password (%s): %s" in entrypoint
    assert "rm -f /root/.config/code-server/config.yaml" in entrypoint
    assert "MSgouUQP4vhET" not in dockerfile
    assert "MSgouUQP4vhET" not in entrypoint


def test_docker_image_installs_latest_code_server_and_runs_it_externally() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    supervisor = (ROOT / "docker" / "supervisord.conf").read_text(encoding="utf-8")

    assert "shellinabox" not in dockerfile.lower()
    assert "shellinabox" not in supervisor.lower()
    assert "https://code-server.dev/install.sh" in dockerfile
    assert "CODE_SERVER_PORT=4200" in dockerfile
    assert "[program:code-server]" in supervisor
    assert "--bind-addr 0.0.0.0:%(ENV_CODE_SERVER_PORT)s" in supervisor
    assert "--auth password" in supervisor


def test_docker_image_installs_ossutil_with_official_installer() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "https://gosspublic.alicdn.com/ossutil/install.sh" in dockerfile
    assert "ossutil --version" in dockerfile
