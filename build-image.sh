#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${IMAGE_NAME:-anima-lora-webui}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
BUILD_CONTEXT="${BUILD_CONTEXT:-.}"

if [ "${1:-}" != "" ]; then
    if [[ "$1" == *:* ]]; then
        IMAGE_NAME="${1%%:*}"
        IMAGE_TAG="${1##*:}"
    else
        IMAGE_NAME="$1"
    fi
fi

IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_BIN=(docker)
elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    DOCKER_BIN=(sudo docker)
else
    echo "[build-image] docker is unavailable or requires privileges that are not configured." >&2
    exit 1
fi

DOCKER_CMD=("${DOCKER_BIN[@]}" build -f "$DOCKERFILE" -t "$IMAGE_REF")

if [ "${NO_CACHE:-0}" = "1" ]; then
    DOCKER_CMD+=(--no-cache)
fi

if [ -n "${BUILD_PLATFORM:-}" ]; then
    DOCKER_CMD+=(--platform "$BUILD_PLATFORM")
fi

if [ -n "${BUILD_TARGET:-}" ]; then
    DOCKER_CMD+=(--target "$BUILD_TARGET")
fi

if [ -n "${BUILD_ARGS:-}" ]; then
    # shellcheck disable=SC2206
    EXTRA_BUILD_ARGS=(${BUILD_ARGS})
    DOCKER_CMD+=("${EXTRA_BUILD_ARGS[@]}")
fi

DOCKER_CMD+=("$BUILD_CONTEXT")

echo "[build-image] root:       $ROOT_DIR"
echo "[build-image] dockerfile: $DOCKERFILE"
echo "[build-image] context:    $BUILD_CONTEXT"
echo "[build-image] image:      $IMAGE_REF"
if [ "${NO_CACHE:-0}" = "1" ]; then
    echo "[build-image] no-cache:   enabled"
fi
if [ -n "${BUILD_PLATFORM:-}" ]; then
    echo "[build-image] platform:   $BUILD_PLATFORM"
fi
if [ -n "${BUILD_TARGET:-}" ]; then
    echo "[build-image] target:     $BUILD_TARGET"
fi
echo "[build-image] command:    ${DOCKER_CMD[*]}"

"${DOCKER_CMD[@]}"

echo
echo "[build-image] completed: $IMAGE_REF"
