#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import cantools


DBC_CATALOG_FILENAME = "dbc_catalog.json"


def _legacy_catalog(config_dir: Path, interfaces: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    available = sorted(
        path
        for path in config_dir.glob("*.dbc")
        if path.name != DBC_CATALOG_FILENAME
    )
    interface_filenames = {f"{interface}.dbc" for interface in interfaces}
    fallback = next((path for path in available if path.name not in interface_filenames), None)
    fallback = fallback or (available[0] if available else None)

    catalog: dict[str, list[dict[str, Any]]] = {}
    for interface in interfaces:
        specific = config_dir / f"{interface}.dbc"
        path = specific if specific.exists() else fallback
        catalog[interface] = []
        if path is not None:
            catalog[interface].append(
                {
                    "path": relative_dbc_path(config_dir, path),
                    "enabled": True,
                    "priority": 0,
                }
            )
    return catalog


def _normalize_catalog_path(config_dir: Path, path_text: str) -> str:
    candidate = Path(path_text)
    if candidate.is_absolute():
        candidate = candidate.relative_to(config_dir)

    normalized = Path(str(candidate).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"DBC path must stay inside config/: {path_text}")
    return normalized.as_posix()


def relative_dbc_path(config_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(config_dir.resolve()).as_posix()


def load_dbc_catalog(config_dir: Path, interfaces: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    catalog_path = config_dir / DBC_CATALOG_FILENAME
    if not catalog_path.exists():
        return _legacy_catalog(config_dir, interfaces)

    raw_catalog = json.loads(catalog_path.read_text() or "{}")
    catalog: dict[str, list[dict[str, Any]]] = {interface: [] for interface in interfaces}
    for interface in interfaces:
        for raw_entry in raw_catalog.get(interface, []):
            path_text = str(raw_entry.get("path", "")).strip()
            if not path_text:
                continue
            catalog[interface].append(
                {
                    "path": _normalize_catalog_path(config_dir, path_text),
                    "enabled": bool(raw_entry.get("enabled", True)),
                    "priority": int(raw_entry.get("priority", 0)),
                }
            )
    return catalog


def save_dbc_catalog(
    config_dir: Path,
    catalog: Mapping[str, Sequence[Mapping[str, Any]]],
    interfaces: Sequence[str],
) -> None:
    payload = {
        interface: [
            {
                "path": _normalize_catalog_path(config_dir, str(entry["path"])),
                "enabled": bool(entry.get("enabled", True)),
                "priority": int(entry.get("priority", 0)),
            }
            for entry in catalog.get(interface, [])
        ]
        for interface in interfaces
    }
    (config_dir / DBC_CATALOG_FILENAME).write_text(json.dumps(payload, indent=2) + "\n")


def sort_dbc_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "path": str(entry["path"]),
                "enabled": bool(entry.get("enabled", True)),
                "priority": int(entry.get("priority", 0)),
            }
            for entry in entries
        ),
        key=lambda entry: (-entry["priority"], Path(entry["path"]).name.lower(), entry["path"]),
    )


def resolve_active_dbc_paths(
    config_dir: Path,
    interfaces: Sequence[str],
) -> dict[str, list[Path]]:
    catalog = load_dbc_catalog(config_dir, interfaces)
    active_paths: dict[str, list[Path]] = {}
    for interface in interfaces:
        entries = [
            entry
            for entry in catalog.get(interface, [])
            if entry.get("enabled", True)
        ]
        active_paths[interface] = [
            config_dir / entry["path"]
            for entry in sorted(
                entries,
                key=lambda item: (int(item.get("priority", 0)), str(item["path"])),
            )
            if (config_dir / entry["path"]).exists()
        ]
    return active_paths


def reserve_dbc_upload_path(config_dir: Path, interface: str, filename: str) -> Path:
    basename = Path(filename).name.strip()
    if not basename:
        raise ValueError("Uploaded DBC filename is empty")

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(basename).stem).strip("._") or interface
    target_dir = config_dir / "dbcs" / interface
    target_dir.mkdir(parents=True, exist_ok=True)

    candidate = target_dir / f"{stem}.dbc"
    suffix = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}-{suffix}.dbc"
        suffix += 1
    return candidate


def load_merged_dbc(paths: Sequence[Path]) -> cantools.database.Database:
    database = cantools.database.Database()
    for path in paths:
        database.add_dbc_file(str(path))
    return database


def load_signal_metadata(interface_paths: Mapping[str, Sequence[Path]]) -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    for paths in interface_paths.values():
        db = load_merged_dbc(paths)
        for message in db.messages:
            for signal in message.signals:
                choices = [
                    {"value": value, "label": str(label)}
                    for value, label in sorted((signal.choices or {}).items())
                ]
                metadata[signal.name] = {"name": signal.name, "choices": choices}
    return dict(sorted(metadata.items()))


def load_signal_names(interface_paths: Mapping[str, Sequence[Path]]) -> list[str]:
    return list(load_signal_metadata(interface_paths))
