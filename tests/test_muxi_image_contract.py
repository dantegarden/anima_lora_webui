from __future__ import annotations

import asyncio
from pathlib import Path

from web.services.training import gpu as gpu_helpers


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile.muxi"
REQUIREMENTS = ROOT / "requirements-muxi.txt"


def test_muxi_dockerfile_reuses_metax_runtime() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM hub.6scloud.com/d1s6t1r3jrms73f3ltpg/comfyui-metax-c500-torch2dot10:v20261117-da3-colormap" in dockerfile
    assert "requirements-muxi.txt" in dockerfile
    assert "venv --system-site-packages" in dockerfile
    assert "uv sync" not in dockerfile
    assert "uv python install 3.13" not in dockerfile
    assert "ENV PATH=/workspace/anima_lora_webui/.venv/bin:/root/.local/bin:${PATH}" in dockerfile
    assert 'ENTRYPOINT ["/usr/bin/dumb-init", "--", "/usr/local/bin/entrypoint.sh"]' in dockerfile
    assert "dumb-init \\" in dockerfile


def test_muxi_requirements_do_not_install_cuda_only_wheels() -> None:
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    active_lines = [
        line.strip() for line in requirements.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    lowered = "\n".join(active_lines).lower()
    packages = {line.split("==", 1)[0].strip().lower() for line in active_lines}

    for excluded in ("torch", "torchvision", "torchaudio", "flash-attn", "bitsandbytes", "sam3"):
        assert excluded not in packages
    for included in ("accelerate==", "transformers==", "diffusers==", "aiohttp==", "numpy=="):
        assert included in lowered


def test_gpu_helpers_fall_back_to_mx_smi(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, stdout: bytes):
            self.stdout = stdout
            self.returncode = 0

        async def communicate(self):
            return self.stdout, b""

    calls: list[str] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(str(args[0]))
        if args[0] == "nvidia-smi":
            raise FileNotFoundError(str(args[0]))
        return FakeProcess(b"0, MetaX C500, 65536\n")

    gpus = asyncio.run(
        gpu_helpers.list_available_gpus(
            create_subprocess_exec=fake_create_subprocess_exec,
            stdout_pipe=object(),
            stderr_devnull=object(),
        )
    )

    assert calls == ["nvidia-smi", "mx-smi"]
    assert gpus == [
        {
            "index": 0,
            "name": "MetaX C500",
            "label": "GPU 0 · MetaX C500",
            "memory_total_mb": 65536,
            "memory_total_gb": 64.0,
        }
    ]


def test_gpu_stats_fall_back_to_mx_smi() -> None:
    class FakeProcess:
        def __init__(self, stdout: bytes):
            self.stdout = stdout
            self.returncode = 0

        async def communicate(self):
            return self.stdout, b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        if args[0] == "nvidia-smi":
            raise FileNotFoundError(str(args[0]))
        return FakeProcess(b"0, 2048, 65536, 37, 0\n")

    stats = asyncio.run(
        gpu_helpers.get_gpu_stats(
            [0],
            create_subprocess_exec=fake_create_subprocess_exec,
            stdout_pipe=object(),
            stderr_devnull=object(),
        )
    )

    assert stats["gpu_index"] == 0
    assert stats["vram_used_gb"] == 2
    assert stats["vram_total_gb"] == 64
    assert stats["gpu_util"] == 37


def test_apply_gpu_whitelist_sets_maca_visible_devices() -> None:
    env: dict[str, str] = {}

    gpu_helpers.apply_gpu_whitelist(env, [1])

    assert env["CUDA_VISIBLE_DEVICES"] == "1"
    assert env["MACA_VISIBLE_DEVICES"] == "1"
