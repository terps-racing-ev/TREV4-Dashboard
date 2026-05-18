#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import cantools


def load_signal_metadata(paths: list[Path]) -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    for path in paths:
        db = cantools.database.load_file(str(path))
        for message in db.messages:
            for signal in message.signals:
                choices = [
                    {"value": value, "label": str(label)}
                    for value, label in sorted((signal.choices or {}).items())
                ]
                metadata[signal.name] = {"name": signal.name, "choices": choices}
    return dict(sorted(metadata.items()))


def load_signal_names(paths: list[Path]) -> list[str]:
    return list(load_signal_metadata(paths))
