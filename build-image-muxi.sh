#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

export DOCKERFILE="${DOCKERFILE:-Dockerfile.muxi}"
export IMAGE_NAME="${IMAGE_NAME:-hub.6scloud.com/d1s6t1r3jrms73f3ltpg/anima-lora-webui}"
export IMAGE_TAG="${IMAGE_TAG:-muxi-20261121-v1}"

exec bash ./build-image.sh "$@"
