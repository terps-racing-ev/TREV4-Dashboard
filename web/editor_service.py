from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

import pygame
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.colors import named_colors, parse_color
from app.dashboard import Dashboard
from app.dbc_utils import load_signal_metadata
from app.gauge_config import (
    DISPLAY_SIZE,
    GAUGE_SPECS,
    load_dashboard_config,
    normalize_gauge_config,
    save_dashboard_config,
    validate_layout,
)
from app.shared_data import LatestValuesTable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"
WEB_DIST_DIR = ROOT / "web" / "dist"


def _normalize_dashboard_config(raw: dict[str, Any]) -> dict[str, Any]:
    display = raw.get("display", {})
    normalized = {
        "display": {
            "width": DISPLAY_SIZE[0],
            "height": DISPLAY_SIZE[1],
            "bg_color": list(parse_color(display.get("bg_color", [0, 0, 0])) or (0, 0, 0)),
        },
        "gauges": [normalize_gauge_config(gauge) for gauge in raw.get("gauges", [])],
    }
    return normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class EditorState:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = config_path
        self.saved = load_dashboard_config(config_path)
        self.draft = copy.deepcopy(self.saved)
        self.preview_values = LatestValuesTable()
        self.signal_metadata = load_signal_metadata(sorted(CONFIG_DIR.glob("*.dbc")))
        self.signal_names = list(self.signal_metadata)
        self._seed_enum_preview_values()

    def _seed_enum_preview_values(self) -> None:
        raw_values: dict[str, Any] = {}
        display_values: dict[str, Any] = {}
        for name, metadata in self.signal_metadata.items():
            choices = metadata["choices"]
            if choices:
                first_choice = choices[0]
                raw_values[name] = first_choice["value"]
                display_values[name] = first_choice["label"]
        self.preview_values.update(raw_values, display_values)

    def update_preview_values(self, payload: dict[str, Any]) -> None:
        display_values: dict[str, Any] = {}
        for name, value in payload.items():
            choices = self.signal_metadata.get(name, {}).get("choices", [])
            choice = next((item for item in choices if item["value"] == value), None)
            if choice is not None:
                display_values[name] = choice["label"]
        self.preview_values.update(payload, display_values or None)

    def response_payload(self) -> dict[str, Any]:
        return {
            "saved": self.saved,
            "draft": self.draft,
            "validation": self.validation_payload(),
        }

    def validation_payload(self) -> dict[str, list[str]]:
        return {"errors": [], "warnings": validate_layout(self.draft, signal_names=set(self.signal_names))}

    def replace_draft(self, raw: dict[str, Any]) -> dict[str, Any]:
        self.draft = _normalize_dashboard_config(raw)
        return self.response_payload()

    def save(self) -> dict[str, Any]:
        normalized = _normalize_dashboard_config(self.draft)
        save_dashboard_config(normalized, self.config_path)
        self.saved = load_dashboard_config(self.config_path)
        self.draft = copy.deepcopy(self.saved)
        return self.response_payload()

    def render_preview(self) -> bytes:
        dashboard = Dashboard(self.preview_values, config=self.draft)
        frame = dashboard.render_frame()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            pygame.image.save(frame, str(temp_path))
            return temp_path.read_bytes()
        finally:
            temp_path.unlink(missing_ok=True)


def create_app(config_path: Path = DEFAULT_CONFIG_PATH) -> FastAPI:
    app = FastAPI(title="Dashboard Editor")
    state = EditorState(config_path)
    app.state.editor = state

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return state.response_payload()

    @app.put("/api/draft")
    def put_draft(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return state.replace_draft(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.post("/api/save")
    def save() -> dict[str, Any]:
        try:
            return state.save()
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.post("/api/import")
    def import_config(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return state.replace_draft(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.get("/api/export")
    def export_config() -> Response:
        body = json.dumps(state.draft, indent=2) + "\n"
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="dashboard-config.json"'},
        )

    @app.get("/api/gauge-types")
    def gauge_types() -> dict[str, Any]:
        return {
            type_name: {
                "type": type_name,
                "fields": [
                    {
                        "name": field.name,
                        "label": field.label,
                        "kind": field.kind,
                        "default": _json_safe(field.default),
                    }
                    for field in spec.fields
                ],
            }
            for type_name, spec in GAUGE_SPECS.items()
        }

    @app.get("/api/signals")
    def signals() -> dict[str, Any]:
        return {"signals": state.signal_names, "metadata": state.signal_metadata}

    @app.get("/api/colors")
    def colors() -> dict[str, dict[str, list[int]]]:
        return {"colors": {name: list(value) for name, value in named_colors().items()}}

    @app.put("/api/mock-values")
    def mock_values(payload: dict[str, Any]) -> dict[str, Any]:
        state.update_preview_values(payload)
        return {"values": state.preview_values.get_snapshot()}

    @app.get("/api/preview.png")
    def preview() -> Response:
        try:
            return Response(content=state.render_preview(), media_type="image/png")
        except Exception as exc:
            return JSONResponse(status_code=400, content={"errors": [str(exc)], "warnings": []})

    if WEB_DIST_DIR.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST_DIR / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIST_DIR / "index.html")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            candidate = WEB_DIST_DIR / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(WEB_DIST_DIR / "index.html")
    else:
        @app.get("/")
        def missing_frontend() -> dict[str, str]:
            return {"message": "Frontend not built. Run the web build first."}

    return app


app = create_app()
