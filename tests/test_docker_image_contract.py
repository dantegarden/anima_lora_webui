from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"


def test_root_password_default_is_owned_by_entrypoint_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert "SSH_PASSWORD=" not in dockerfile
    assert 'SSH_PASSWORD="${SSH_PASSWORD:-bizyair}"' in entrypoint
    assert "MSgouUQP4vhET" not in dockerfile
    assert "MSgouUQP4vhET" not in entrypoint


def test_docker_image_installs_versioned_ossutil_for_target_architecture() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG OSSUTIL_VERSION=" in dockerfile
    assert "ARG TARGETARCH" in dockerfile
    assert "ossutil-${OSSUTIL_VERSION}-linux-${TARGETARCH}.zip" in dockerfile
    assert "/usr/local/bin/ossutil" in dockerfile
    assert "ossutil version" in dockerfile
