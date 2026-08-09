"""Lightweight image scan helpers for preprocess-time decode failures."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from PIL import Image


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".avif",
    ".jxl",
}


@dataclass(frozen=True)
class ImageScanFailure:
    path: Path
    stage: str
    error_type: str
    message: str


def _is_image_path(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _iter_image_paths(
    src: Path,
    *,
    recursive: bool,
    path_pattern: str | None,
) -> list[Path]:
    pattern = (path_pattern or "*").strip() or "*"
    paths = src.rglob("*") if recursive else src.glob("*")
    image_paths = [path for path in paths if _is_image_path(path)]
    image_paths.sort()
    if pattern == "*":
        return image_paths

    patterns = [item.strip() for item in pattern.split("|") if item.strip()]
    if not patterns:
        return image_paths

    return [
        path
        for path in image_paths
        if any(fnmatchcase(path.relative_to(src).as_posix(), item) for item in patterns)
    ]


def check_image_for_preprocess_failure(
    path: Path,
    *,
    check_png_text: bool = True,
) -> ImageScanFailure | None:
    """Return the preprocess-read failure for ``path``, or ``None``."""
    try:
        with Image.open(path) as src:
            if check_png_text and src.format == "PNG":
                try:
                    getattr(src, "text", None)
                except Exception as e:  # noqa: BLE001
                    return ImageScanFailure(
                        path=path,
                        stage="png_text",
                        error_type=type(e).__name__,
                        message=str(e),
                    )

            try:
                rgb = src.convert("RGB")
                rgb.load()
            except Exception as e:  # noqa: BLE001
                return ImageScanFailure(
                    path=path,
                    stage="decode_rgb",
                    error_type=type(e).__name__,
                    message=str(e),
                )
    except Exception as e:  # noqa: BLE001
        return ImageScanFailure(
            path=path,
            stage="open",
            error_type=type(e).__name__,
            message=str(e),
        )
    return None


def scan_images_for_preprocess_failures(
    src: Path,
    *,
    recursive: bool = False,
    path_pattern: str | None = None,
    check_png_text: bool = True,
) -> list[ImageScanFailure]:
    """Scan ``src`` and return files that fail the preprocess-read path."""
    failures: list[ImageScanFailure] = []
    for path in _iter_image_paths(src, recursive=recursive, path_pattern=path_pattern):
        failure = check_image_for_preprocess_failure(
            path,
            check_png_text=check_png_text,
        )
        if failure is not None:
            failures.append(failure)
    return failures
