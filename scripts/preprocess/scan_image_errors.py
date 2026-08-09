#!/usr/bin/env python3
"""Scan a dataset directory for images that fail preprocess-time decoding.

This targets the same failure class seen during resize:

- PNG ``.text`` metadata access raising during ``_collect_metadata()``
- decode / RGB conversion failures that only appear after ``Image.open()``

Useful before a long preprocess run when you want a list of problematic files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from library.image_scan import scan_images_for_preprocess_failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        type=str,
        required=True,
        help="Source image directory to scan.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Walk subfolders under --src.",
    )
    parser.add_argument(
        "--path_pattern",
        type=str,
        default="*",
        help="Optional relative-path glob filter. Use | to combine patterns.",
    )
    parser.add_argument(
        "--no_check_png_text",
        action="store_true",
        help="Skip the PNG .text probe and only force a decode via RGB conversion.",
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="Print paths relative to --src instead of absolute paths.",
    )
    args = parser.parse_args()

    src = Path(args.src)
    failures = scan_images_for_preprocess_failures(
        src,
        recursive=args.recursive,
        path_pattern=args.path_pattern,
        check_png_text=not args.no_check_png_text,
    )

    if not failures:
        print(f"OK: no preprocess-time decode failures found under {src}")
        return

    print(f"Found {len(failures)} problematic image(s) under {src}:")
    for failure in failures:
        path = failure.path.relative_to(src) if args.relative else failure.path
        print(
            f"{path} | stage={failure.stage} | "
            f"{failure.error_type}: {failure.message}"
        )

    raise SystemExit(1)


if __name__ == "__main__":
    main()
