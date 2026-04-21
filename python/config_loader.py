#!/usr/bin/env python3
"""
Load prod_config.json and prod.dbc from local paths; sync from USB when a
removable drive has these files so the local copies are updated.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CONFIG_FILENAME = "prod_config.json"
DBC_FILENAME = "prod.dbc"

# Project root: parent of python/ (this file lives in python/config_loader.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _safe_iterdir(path: Path) -> list[Path]:
    """Return directory entries, skipping paths that cannot be read."""
    try:
        return list(path.iterdir())
    except OSError:
        return []


def get_local_config_path() -> Path:
    """Return the fixed local prod_config.json path (project root)."""
    return _PROJECT_ROOT / CONFIG_FILENAME


def get_local_dbc_path() -> Path:
    """Return the fixed local prod.dbc path (project root)."""
    if sys.platform == "win32":
        return _PROJECT_ROOT / "dbc" / DBC_FILENAME
    else:
        return _PROJECT_ROOT / DBC_FILENAME

def get_local_dbc_folder() -> Path:
    """
    Return the folder where local DBC files live for this platform.
    This keeps folder-based loading aligned with the original get_local_dbc_path().
    """
    return get_local_dbc_path().parent


def get_local_dbc_paths() -> list[Path]:
    """Return all local .dbc files in the dbc folder."""
    root = get_local_dbc_folder()
    if not root.is_dir():
        return []
    return sorted(path for path in _safe_iterdir(root) if path.is_file() and path.suffix.lower() == ".dbc")


def get_usb_mount_paths() -> list[Path]:
    """
    Return candidate root paths for removable media (USB drives).
    Platform-specific: macOS /Volumes, Linux /media and /run/media, Windows drives.
    """
    paths: list[Path] = []
    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            paths.extend(p for p in _safe_iterdir(volumes) if p.is_dir() and not p.name.startswith("."))
    elif sys.platform == "linux":
        for base in ("/media", "/run/media"):
            p = Path(base)
            if not p.is_dir():
                continue
            for item in _safe_iterdir(p):
                if item.is_dir():
                    paths.append(item)  # e.g. /media/MyUSB or /run/media/username
                    for sub in _safe_iterdir(item):
                        if sub.is_dir():
                            paths.append(sub)  # e.g. /run/media/username/MyUSB
    elif sys.platform == "win32":
        import string
        for letter in string.ascii_uppercase[1:]:  # D: through Z:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                paths.append(drive)
    return list(dict.fromkeys(paths))  # dedupe


def _find_file_on_usb(filename: str) -> Path | None:
    """
    Search USB mount paths for a file by name.
    Checks root of each mount and one level down.
    Returns the first path where the file exists, or None.
    """
    for root in get_usb_mount_paths():
        candidate = root / filename
        if candidate.is_file():
            return candidate
        for sub in _safe_iterdir(root):
            if sub.is_dir():
                candidate = sub / filename
                try:
                    if candidate.is_file():
                        return candidate
                except PermissionError:
                        pass
    return None


def find_config_on_usb() -> Path | None:
    """Search USB mount paths for prod_config.json."""
    return _find_file_on_usb(CONFIG_FILENAME)


def find_dbc_on_usb() -> Path | None:
    """Search USB mount paths for prod.dbc."""
    return _find_file_on_usb(DBC_FILENAME)


def _find_usb_dbc_folder() -> Path | None:
    """Return the first folder on USB media that contains at least one .dbc file."""
    for root in get_usb_mount_paths():
        if any(path.is_file() and path.suffix.lower() == ".dbc" for path in _safe_iterdir(root)):
            return root
        for sub in _safe_iterdir(root):
            if sub.is_dir() and any(path.is_file() and path.suffix.lower() == ".dbc" for path in _safe_iterdir(sub)):
                return sub
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


def sync_dbc_from_usb() -> bool:
    """
    If prod.dbc exists on a USB drive, copy it to the local path (overwrite).
    Returns True if a copy was performed.
    """
    src = find_dbc_on_usb()
    if src is None:
        return False
    dst = get_local_dbc_path()
    try:
        shutil.copy2(src, dst)
        print(f"Updated local {DBC_FILENAME} from USB: {src}")
        return True
    except OSError as e:
        print(f"Failed to sync DBC from USB ({src}): {e}")
        return False


def sync_dbcs_from_usb() -> bool:
    """Copy every .dbc file from the USB dbc folder into the local dbc folder."""
    src_root = _find_usb_dbc_folder()
    if src_root is None:
        return False

    dst_root = get_local_dbc_folder()
    dst_root.mkdir(parents=True, exist_ok=True)

    copied = False
    try:
        for src in sorted(path for path in _safe_iterdir(src_root) if path.is_file() and path.suffix.lower() == ".dbc"):
            shutil.copy2(src, dst_root / src.name)
            print(f"Updated local {src.name} from USB: {src}")
            copied = True
        return copied
    except OSError as e:
        print(f"Failed to sync DBCs from USB ({src_root}): {e}")
        return False

def find_other_dbcs():
    """
    If there are multiple DBC files that start with prod, combine them into one.
    Destructive way of handling multiple DBCs, but it means i can change less code
    All dbc files will be backed up into a folder
    """
    for path in get_local_dbc_folder().iterdir():
        if path.suffix == ".dbc":
            print(path)
