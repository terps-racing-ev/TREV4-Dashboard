#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .lap_timer import normalize_lap_timer_config
from .shared_data import LatestValuesTable

DISPLAY_SIZE = (800, 480)
BLACK = [0, 0, 0]
WHITE = [255, 255, 255]
GREEN = [0, 200, 0]
RED = [255, 0, 0]
DEFAULT_BRIGHTNESS = 100


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str
    default: Any


@dataclass(frozen=True)
class GaugeSpec:
    type_name: str
    cls: str
    fields: tuple[FieldSpec, ...]

    @property
    def defaults(self) -> dict[str, Any]:
        return {field.name: field.default for field in self.fields}


COMMON_FIELDS = (
    FieldSpec("signal", "Signal", "signal", ""),
    FieldSpec("label", "Label", "text", "GAUGE"),
    FieldSpec("min_val", "Min", "number", 0),
    FieldSpec("max_val", "Max", "number", 100),
    FieldSpec("box_xywh", "Position (x, y, w, h)", "rect", [0, 0, 120, 80]),
    FieldSpec("decimal_places", "Decimals", "int", 0),
    FieldSpec("box_color", "Box Color", "color", None),
    FieldSpec("border_color", "Border Color", "color", WHITE),
    FieldSpec("text_color", "Text Color", "color", WHITE),
)

GRADIENT_FIELDS = (
    FieldSpec("min_color", "Min Color", "color", GREEN),
    FieldSpec("max_color", "Max Color", "color", RED),
    FieldSpec("gradient_text", "Gradient Text", "bool", False),
    FieldSpec("gradient_box", "Gradient Box", "bool", False),
    FieldSpec("gradient_border", "Gradient Border", "bool", False),
)

GAUGE_SPECS: dict[str, GaugeSpec] = {
    "SimpleGauge": GaugeSpec(
        "SimpleGauge",
        "SimpleGauge",
        COMMON_FIELDS
        + GRADIENT_FIELDS
        + (
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
    "UnsignedLinearGauge": GaugeSpec(
        "UnsignedLinearGauge",
        "UnsignedLinearGauge",
        COMMON_FIELDS
        + GRADIENT_FIELDS
        + (
            FieldSpec("fill_color", "Fill", "color", GREEN),
            FieldSpec("gradient_fill", "Gradient Fill", "bool", False),
            FieldSpec("vertical", "Vertical", "bool", True),
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
    "SignedLinearGauge": GaugeSpec(
        "SignedLinearGauge",
        "SignedLinearGauge",
        COMMON_FIELDS
        + GRADIENT_FIELDS
        + (
            FieldSpec("pos_color", "Positive", "color", GREEN),
            FieldSpec("neg_color", "Negative", "color", RED),
            FieldSpec("gradient_fill", "Gradient Fill", "bool", False),
            FieldSpec("vertical", "Vertical", "bool", True),
            FieldSpec("show_value", "Show Value", "bool", True),
        ),
    ),
}


def _resolve_gauge_class(class_name: str) -> Callable[..., Any]:
    from . import gauges

    return getattr(gauges, class_name)


def _normalize_color(value: Any) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("color fields must be null or [r, g, b]")
    color: list[int] = []
    for component in value:
        number = int(component)
        if number < 0 or number > 255:
            raise ValueError("color components must be between 0 and 255")
        color.append(number)
    return color


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
            normalized[field.name] = _normalize_color(value)
        else:
            normalized[field.name] = value

    min_val = normalized["min_val"]
    max_val = normalized["max_val"]
    if max_val < min_val:
        raise ValueError("max_val must be greater than or equal to min_val")
    return normalized


def _normalize_display_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    display = raw or {}
    return {
        "width": DISPLAY_SIZE[0],
        "height": DISPLAY_SIZE[1],
        "bg_color": _normalize_color(display.get("bg_color", BLACK)) or BLACK,
    }


def _normalize_brightness(value: Any) -> int:
    brightness = int(value)
    if brightness < 0 or brightness > 100:
        raise ValueError("brightness must be between 0 and 100")
    return brightness


def normalize_dashboard_config(raw: dict[str, Any]) -> dict[str, Any]:
    dashboard_id = str(raw.get("id") or "").strip()
    if not dashboard_id:
        raise ValueError("Dashboard id is required")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("Dashboard name is required")
    return {
        "id": dashboard_id,
        "name": name,
        "display": _normalize_display_config(raw.get("display")),
        "gauges": [normalize_gauge_config(gauge) for gauge in raw.get("gauges", [])],
    }


def create_default_dashboard_config(
    *,
    dashboard_id: str,
    name: str,
) -> dict[str, Any]:
    return normalize_dashboard_config({"id": dashboard_id, "name": name, "display": {}, "gauges": []})


def normalize_dashboard_library_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw.get("dashboards"), list) or not raw["dashboards"]:
        raise ValueError("Dashboard config must contain a non-empty dashboards list")
    dashboards = [normalize_dashboard_config(dashboard) for dashboard in raw["dashboards"]]
    brightness = _normalize_brightness(raw.get("brightness", DEFAULT_BRIGHTNESS))

    seen_ids: set[str] = set()
    for dashboard in dashboards:
        dashboard_id = dashboard["id"]
        if dashboard_id in seen_ids:
            raise ValueError(f"Duplicate dashboard id: {dashboard_id}")
        seen_ids.add(dashboard["id"])

    active_dashboard_id = str(raw.get("active_dashboard_id") or "")
    if active_dashboard_id not in seen_ids:
        raise ValueError("active_dashboard_id must match a dashboard id")

    return {
        "brightness": brightness,
        "active_dashboard_id": active_dashboard_id,
        "lap_timer": normalize_lap_timer_config(raw.get("lap_timer")),
        "dashboards": dashboards,
    }


def get_dashboard_by_id(library: dict[str, Any], dashboard_id: str | None = None) -> dict[str, Any]:
    dashboards = library.get("dashboards", [])
    if not dashboards:
        raise ValueError("Dashboard library is empty")
    target_id = dashboard_id or library.get("active_dashboard_id")
    dashboard = next((item for item in dashboards if item.get("id") == target_id), None)
    if dashboard is None:
        raise ValueError(f"Unknown dashboard id: {target_id}")
    selected = dict(dashboard)
    selected["brightness"] = _normalize_brightness(library.get("brightness", DEFAULT_BRIGHTNESS))
    return selected


def create_default_gauge_config(gauge_type: str, *, offset: int = 0) -> dict[str, Any]:
    if gauge_type not in GAUGE_SPECS:
        raise ValueError(f"Unknown gauge type: {gauge_type}")
    raw = {"type": gauge_type, **GAUGE_SPECS[gauge_type].defaults}
    raw["box_xywh"] = [20 + offset, 20 + offset, 120, 80]
    return normalize_gauge_config(raw)


def instantiate_gauge(config: dict[str, Any], shared_data: LatestValuesTable) -> Gauge:
    cfg = normalize_gauge_config(config)
    gauge_type = cfg.pop("type")
    cls = _resolve_gauge_class(GAUGE_SPECS[gauge_type].cls)
    cfg["box_xywh"] = tuple(cfg["box_xywh"])
    for name, value in list(cfg.items()):
        if name.endswith("_color") and value is not None:
            cfg[name] = tuple(value)
    cfg["shared_data"] = shared_data
    return cls(**cfg)


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


def validate_dashboard_library(config: dict[str, Any], *, signal_names: set[str] | None = None) -> dict[str, list[str]]:
    library = normalize_dashboard_library_config(config)
    return {
        dashboard["id"]: validate_layout(dashboard, signal_names=signal_names)
        for dashboard in library.get("dashboards", [])
    }


def load_dashboard_library_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        raw = json.load(f)
    return normalize_dashboard_library_config(raw)


def load_dashboard_config(path: Path) -> dict[str, Any]:
    return get_dashboard_by_id(load_dashboard_library_config(path))


def save_dashboard_library_config(config: dict[str, Any], path: Path) -> None:
    normalized = normalize_dashboard_library_config(config)
    with path.open("w") as f:
        json.dump(normalized, f, indent=2)
        f.write("\n")


def field_specs_for(gauge_type: str) -> tuple[FieldSpec, ...]:
    return GAUGE_SPECS[gauge_type].fields
