#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .colors import named_colors, parse_color
from .gauges import Gauge, GradientGauge, SignedLinearGauge, SimpleGauge, UnsignedLinearGauge
from .shared_data import LatestValuesTable

DISPLAY_SIZE = (800, 480)
ColorValue = str | list[int] | None


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str
    default: Any


@dataclass(frozen=True)
class GaugeSpec:
    type_name: str
    cls: type[Gauge]
    fields: tuple[FieldSpec, ...]

    @property
    def defaults(self) -> dict[str, Any]:
        return {field.name: field.default for field in self.fields}


COMMON_FIELDS = (
    FieldSpec("signal", "Signal", "signal", ""),
    FieldSpec("label", "Label", "text", "GAUGE"),
    FieldSpec("min_val", "Min", "number", 0),
    FieldSpec("max_val", "Max", "number", 100),
    FieldSpec("box_xywh", "Box", "rect", [0, 0, 120, 80]),
    FieldSpec("decimal_places", "Decimals", "int", 0),
    FieldSpec("box_color", "Box Color", "color", None),
    FieldSpec("border_color", "Border Color", "color", "WHITE"),
    FieldSpec("text_color", "Text Color", "color", "WHITE"),
)

GAUGE_SPECS: dict[str, GaugeSpec] = {
    "SimpleGauge": GaugeSpec("SimpleGauge", SimpleGauge, COMMON_FIELDS),
    "GradientGauge": GaugeSpec(
        "GradientGauge",
        GradientGauge,
        COMMON_FIELDS
        + (
            FieldSpec("min_color", "Min Color", "color", "GREEN"),
            FieldSpec("max_color", "Max Color", "color", "RED"),
            FieldSpec("gradient_text", "Gradient Text", "bool", True),
            FieldSpec("gradient_box", "Gradient Box", "bool", False),
            FieldSpec("gradient_border", "Gradient Border", "bool", False),
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
    "UnsignedLinearGauge": GaugeSpec(
        "UnsignedLinearGauge",
        UnsignedLinearGauge,
        COMMON_FIELDS
        + (
            FieldSpec("fill_color", "Fill", "color", "GREEN"),
            FieldSpec("vertical", "Vertical", "bool", True),
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
    "SignedLinearGauge": GaugeSpec(
        "SignedLinearGauge",
        SignedLinearGauge,
        COMMON_FIELDS
        + (
            FieldSpec("pos_color", "Positive", "color", "GREEN"),
            FieldSpec("neg_color", "Negative", "color", "RED"),
            FieldSpec("vertical", "Vertical", "bool", True),
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
}


def _coerce_color(value: Any, default: ColorValue) -> ColorValue:
    if value is None:
        return None
    if value == "":
        return default
    if isinstance(value, str) and value.upper() in named_colors():
        return value.upper()
    color = parse_color(value)
    return None if color is None else list(color[:3])


def normalize_gauge_config(raw: dict[str, Any]) -> dict[str, Any]:
    gauge_type = raw.get("type")
    if gauge_type not in GAUGE_SPECS:
        raise ValueError(f"Unknown gauge type: {gauge_type}")

    spec = GAUGE_SPECS[gauge_type]
    normalized: dict[str, Any] = {"type": gauge_type}
    for field in spec.fields:
        value = raw.get(field.name, field.default)
        if field.kind == "rect":
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                raise ValueError(f"{field.name} must contain four numbers")
            normalized[field.name] = [int(v) for v in value]
        elif field.kind == "int":
            normalized[field.name] = int(value)
        elif field.kind == "number":
            normalized[field.name] = float(value) if isinstance(value, str) and "." in value else value
        elif field.kind == "bool":
            normalized[field.name] = bool(value)
        elif field.kind == "color":
            color = _coerce_color(value, field.default)
            normalized[field.name] = color
        else:
            normalized[field.name] = value

    min_val = normalized["min_val"]
    max_val = normalized["max_val"]
    if max_val < min_val:
        raise ValueError("max_val must be greater than or equal to min_val")
    return normalized


def create_default_gauge_config(gauge_type: str, *, offset: int = 0) -> dict[str, Any]:
    if gauge_type not in GAUGE_SPECS:
        raise ValueError(f"Unknown gauge type: {gauge_type}")
    raw = {"type": gauge_type, **GAUGE_SPECS[gauge_type].defaults}
    raw["box_xywh"] = [20 + offset, 20 + offset, 120, 80]
    return normalize_gauge_config(raw)


def instantiate_gauge(config: dict[str, Any], shared_data: LatestValuesTable) -> Gauge:
    cfg = normalize_gauge_config(config)
    gauge_type = cfg.pop("type")
    cfg["box_xywh"] = tuple(cfg["box_xywh"])
    for name, value in list(cfg.items()):
        if name.endswith("_color") and value is not None:
            cfg[name] = tuple(parse_color(value) or ())
    cfg["shared_data"] = shared_data
    return GAUGE_SPECS[gauge_type].cls(**cfg)


def validate_layout(config: dict[str, Any], *, signal_names: set[str] | None = None) -> list[str]:
    warnings: list[str] = []
    gauges = config.get("gauges", [])
    for index, raw in enumerate(gauges):
        try:
            cfg = normalize_gauge_config(raw)
        except Exception as exc:
            warnings.append(f"Gauge {index + 1}: {exc}")
            continue

        x, y, w, h = cfg["box_xywh"]
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > DISPLAY_SIZE[0] or y + h > DISPLAY_SIZE[1]:
            warnings.append(f"Gauge {index + 1}: box is outside the {DISPLAY_SIZE[0]}x{DISPLAY_SIZE[1]} canvas")
        if signal_names is not None and cfg["signal"] and cfg["signal"] not in signal_names:
            warnings.append(f"Gauge {index + 1}: unknown signal '{cfg['signal']}'")

    return warnings


def load_dashboard_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        raw = json.load(f)
    display = raw.get("display", {})
    display = {
        "width": DISPLAY_SIZE[0],
        "height": DISPLAY_SIZE[1],
        "bg_color": list(parse_color(display.get("bg_color", [0, 0, 0])) or (0, 0, 0)),
    }
    gauges = [normalize_gauge_config(gauge) for gauge in raw.get("gauges", [])]
    return {"display": display, "gauges": gauges}


def save_dashboard_config(config: dict[str, Any], path: Path) -> None:
    normalized = {
        "display": {
            "width": DISPLAY_SIZE[0],
            "height": DISPLAY_SIZE[1],
            "bg_color": list(parse_color(config.get("display", {}).get("bg_color", [0, 0, 0])) or (0, 0, 0)),
        },
        "gauges": [normalize_gauge_config(gauge) for gauge in config.get("gauges", [])],
    }
    with path.open("w") as f:
        json.dump(normalized, f, indent=2)
        f.write("\n")


def field_specs_for(gauge_type: str) -> tuple[FieldSpec, ...]:
    return GAUGE_SPECS[gauge_type].fields
