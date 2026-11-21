"""Emit pip constraints for the accelerator packages from the MetaX base image."""

import torch


def main() -> None:
    print(f"torch=={torch.__version__.split('+', 1)[0]}")
    try:
        import torchvision
    except Exception:
        return
    print(f"torchvision=={torchvision.__version__.split('+', 1)[0]}")


if __name__ == "__main__":
    main()
