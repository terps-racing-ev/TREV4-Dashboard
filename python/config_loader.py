#!/usr/bin/env python3
"""
Load prod_config.json from local path; sync from USB when a removable drive
has prod_config.json so the local copy is updated.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CONFIG_FILENAME = "prod_config.json"

# Project root: parent of python/ (this file lives in python/config_loader.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_local_config_path() -> Path:
    """Return the fixed local prod_config.json path (project root)."""
    return _PROJECT_ROOT / CONFIG_FILENAME


def get_usb_mount_paths() -> list[Path]:
    """
    Return candidate root paths for removable media (USB drives).
    Platform-specific: macOS /Volumes, Linux /media and /run/media, Windows drives.
    """
    paths: list[Path] = []
    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            paths.extend(p for p in volumes.iterdir() if p.is_dir() and not p.name.startswith("."))
    elif sys.platform == "linux":
        for base in ("/media", "/run/media"):
            p = Path(base)
            if not p.is_dir():
                continue
            for item in p.iterdir():
                if item.is_dir():
                    paths.append(item)  # e.g. /media/MyUSB or /run/media/username
                    for sub in item.iterdir():
                        if sub.is_dir():
                            paths.append(sub)  # e.g. /run/media/username/MyUSB
    elif sys.platform == "win32":
        import string
        for letter in string.ascii_uppercase[1:]:  # D: through Z:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                paths.append(drive)
    return list(dict.fromkeys(paths))  # dedupe


def find_config_on_usb() -> Path | None:
    """
    Search USB mount paths for prod_config.json.
    Checks root of each mount and one level down (e.g. mount/prod_config.json or mount/gauges/prod_config.json).
    Returns the first path where the file exists, or None.
    """
    for root in get_usb_mount_paths():
        # Direct at root
        candidate = root / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        # One level down (e.g. gauges/prod_config.json)
        for sub in root.iterdir():
            if sub.is_dir():
                candidate = sub / CONFIG_FILENAME
                if candidate.is_file():
                    return candidate
    return None


def sync_config_from_usb() -> bool:
    """
    If prod_config.json exists on a USB drive, copy it to the local path (overwrite).
    Validates JSON before overwriting. Returns True if a copy was performed.
    """
    src = find_config_on_usb()
    if src is None:
        return False
    dst = get_local_config_path()
    try:
        # Validate JSON before overwriting
        with open(src, encoding="utf-8") as f:
            json.load(f)
        shutil.copy2(src, dst)
        print(f"Updated local {CONFIG_FILENAME} from USB: {src}")
        return True
    except (OSError, json.JSONDecodeError) as e:
        print(f"Failed to sync config from USB ({src}): {e}")
        return False
