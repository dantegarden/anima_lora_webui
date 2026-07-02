#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

download_file() {
  local url="$1"
  local target="$2"
  local target_dir
  local tmp

  target_dir="$(dirname "$target")"
  mkdir -p "$target_dir"
  tmp="${target}.part"

  rm -f "$tmp"

  echo "[download] $url"
  echo "[target]   $target"

  # -L follows redirects, -f fails on HTTP errors, and --progress-bar keeps
  # the transfer progress visible without hiding server-side errors.
  curl -fL --progress-bar "$url" -o "$tmp"
  mv -f "$tmp" "$target"

  echo "[done]     $target"
  echo
}

download_file \
  "https://storage.bizyair.cn/assets/train/silvermoonmixAnima_v20.safetensors" \
  "models/diffusion_models/anima-base-v1.0.safetensors"

download_file \
  "https://storage.bizyair.cn/assets/train/qwen_3_06b_base.safetensors" \
  "models/text_encoders/qwen_3_06b_base.safetensors"

download_file \
  "https://storage.bizyair.cn/assets/train/qwen_image_vae.safetensors" \
  "models/vae/qwen_image_vae.safetensors"

echo "All OSS model downloads completed."
