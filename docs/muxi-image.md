# 沐曦（MetaX / MACA）镜像

`Dockerfile.muxi` 是独立于 NVIDIA/CUDA 镜像的沐曦构建。不要把它合并回根
`Dockerfile`：NVIDIA 镜像使用 Python 3.13 + Torch 2.12+cu130，而沐曦镜像必须复用
板卡厂商提供的 Python 3.12 + Torch 2.10+MACA 运行时。

## 基础镜像

```text
hub.6scloud.com/d1s6t1r3jrms73f3ltpg/comfyui-metax-c500-torch2dot10:v20261117-da3-colormap
```

该镜像已经在沐曦 C500 上验证可运行，包含：

- MetaX 驱动 userspace、HPCC/MACA 3.8.2；
- `/opt/hpcc/tools/cu-bridge`、`ht-smi`/`mx-smi` 和 `LD_LIBRARY_PATH`；
- Conda Python 3.12 + MACA 版 PyTorch 2.10。

本项目在基础镜像的 Python 3.12 上创建 `--system-site-packages` venv，因此能继续
使用厂商版 PyTorch，同时安装 WebUI/训练依赖。`requirements-muxi.txt` 不包含
`torch`、`torchvision`、`flash-attn`、`bitsandbytes`、`sam3` 等 CUDA 专用包。

## 构建

```bash
./build-image-muxi.sh
```

也可以指定仓库和标签：

```bash
IMAGE_NAME=hub.6scloud.com/d1s6t1r3jrms73f3ltpg/anima-lora-webui \
IMAGE_TAG=muxi-20261121-v2 \
./build-image-muxi.sh
```

构建脚本会转发给根目录 `build-image.sh`，因此 `NO_CACHE=1`、`BUILD_PLATFORM` 等变量
仍然可用。

## 运行

```bash
docker run --rm -it --gpus all \
  -p 20102:20102 -p 4200:4200 -p 2222:22 \
  -e SSH_PASSWORD=bizyair \
  hub.6scloud.com/d1s6t1r3jrms73f3ltpg/anima-lora-webui:muxi-20261121-v2
```

平台侧通常由容器运行时注入设备，`--gpus all` 只是本地验证写法；请以实际沐曦容器
运行时的设备挂载方式为准。镜像内已带驱动用户态和 MACA 库，不要求宿主机安装
CUDA toolkit。

## 验证

```bash
docker run --rm --entrypoint /workspace/anima_lora_webui/.venv/bin/python \
  hub.6scloud.com/d1s6t1r3jrms73f3ltpg/anima-lora-webui:muxi-20261121-v2 \
  -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"

docker run --rm --entrypoint /workspace/anima_lora_webui/.venv/bin/python \
  hub.6scloud.com/d1s6t1r3jrms73f3ltpg/anima-lora-webui:muxi-20261121-v2 \
  -c "import library, networks, web; print('imports ok')"
```

没有沐曦板卡时 `torch.cuda.is_available()` 应为 `False`，但 `import torch` 必须成功。

## 构建记录

`muxi-20261121-v2`（`sha256:0d86958cd22c683adde7ad521e1cc1edd22f63100ca67811fe9aeac3c57b8940`）
在无沐曦卡的构建机上验证：

- Python 3.12.11，`torch 2.10.0+mars3.8.2.2`，`torchvision 0.25.0+mars3.8.2.2`，`numpy 2.2.6`；
- venv 内没有 CUDA 版 `torch` / `nvidia-*` 运行时包；
- `library`、`networks`、`web` 可导入，`tasks.py web` 返回 HTTP 200；
- `torch.cuda.is_available()` 为 `False` 仅因构建机没有沐曦卡。

注意：基础镜像的 conda 环境里可能有旧版依赖会被 `--system-site-packages` 优先找到。
例如 `peft 0.13.2` 会让 `diffusers 0.37.1` 导入失败，因此 `requirements-muxi.txt`
显式固定 `peft==0.22.0`。新增依赖时若基础镜像里已有旧版本，也要显式写进 requirements。

## 已知限制

- 默认 attention 使用 PyTorch SDPA；没有 CUDA 版 `flash-attn`，显式 `attn_mode=flash`
  会报不可用。
- 镜像默认设置 `TORCH_COMPILE_DISABLE=1`，避免未验证的 MACA inductor 在训练启动时
  失败；确认目标机器可用后可用 `-e TORCH_COMPILE_DISABLE=0` 重新开启。
- 8-bit optimizer（`bitsandbytes`）未安装。
- `sam3` 遮罩流程未安装；需要时应在沐曦环境单独构建。
- GUI（PySide6）未安装，只提供 WebUI/CLI。
