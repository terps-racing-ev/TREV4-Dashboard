from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

import pygame
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.colors import named_colors
from app.dashboard import Dashboard
from app.dbc_utils import load_signal_metadata
from app.gauge_config import (
    GAUGE_SPECS,
    get_dashboard_by_id,
    load_dashboard_library_config,
    normalize_dashboard_library_config,
    save_dashboard_library_config,
    validate_layout,
)
from app.shared_data import LatestValuesTable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"
WEB_DIST_DIR = ROOT / "web" / "dist"
CAN_INTERFACES = ("can0", "can1")


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
        self.saved = load_dashboard_library_config(config_path)
        self.draft = copy.deepcopy(self.saved)
        self.selected_dashboard_id = self.draft["active_dashboard_id"]
        self.preview_values = LatestValuesTable()
        self.signal_metadata = {}
        self.signal_names = []
        self.reload_signal_metadata()
        self._seed_enum_preview_values()

    def active_dbc_paths(self) -> dict[str, Path]:
        available = sorted(CONFIG_DIR.glob("*.dbc"))
        fallback = next((path for path in available if path.name not in {f"{interface}.dbc" for interface in CAN_INTERFACES}), None)
        fallback = fallback or (available[0] if available else None)
        return {
            interface: (CONFIG_DIR / f"{interface}.dbc") if (CONFIG_DIR / f"{interface}.dbc").exists() else fallback
            for interface in CAN_INTERFACES
            if (CONFIG_DIR / f"{interface}.dbc").exists() or fallback is not None
        }

    def dbc_payload(self) -> dict[str, Any]:
        paths = self.active_dbc_paths()
        return {
            "dbcs": {
                interface: {
                    "filename": path.name,
                    "fallback": path.name != f"{interface}.dbc",
                }
                for interface, path in paths.items()
            }
        }

    def reload_signal_metadata(self) -> None:
        unique_paths = sorted(set(self.active_dbc_paths().values()))
        self.signal_metadata = load_signal_metadata(unique_paths)
        self.signal_names = list(self.signal_metadata)

    def replace_dbc(self, interface: str, content: bytes) -> dict[str, Any]:
        if interface not in CAN_INTERFACES:
            raise ValueError(f"Unknown interface: {interface}")
        if not content:
            raise ValueError("DBC upload is empty")

        target = CONFIG_DIR / f"{interface}.dbc"
        temp_target = target.with_suffix(".dbc.tmp")
        temp_target.write_bytes(content)
        temp_target.replace(target)
        self.preview_values.clear()
        self.reload_signal_metadata()
        self._seed_enum_preview_values()
        return self.dbc_payload()

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
            "active_dashboard_id": self.saved["active_dashboard_id"],
            "selected_dashboard_id": self.selected_dashboard_id,
            "validation": self.validation_payload(),
        }

    def selected_dashboard(self) -> dict[str, Any]:
        return get_dashboard_by_id(self.draft, self.selected_dashboard_id)

    def validation_payload(self) -> dict[str, Any]:
        signal_names = set(self.signal_names)
        dashboard_warnings = {
            dashboard["id"]: validate_layout(dashboard, signal_names=signal_names)
            for dashboard in self.draft.get("dashboards", [])
        }
        return {
            "errors": [],
            "warnings": dashboard_warnings.get(self.selected_dashboard()["id"], []),
            "dashboards": dashboard_warnings,
        }

    def replace_draft(self, raw: dict[str, Any]) -> dict[str, Any]:
        self.draft = normalize_dashboard_library_config(raw)
        if not any(dashboard["id"] == self.selected_dashboard_id for dashboard in self.draft["dashboards"]):
            self.selected_dashboard_id = self.draft["active_dashboard_id"]
        return self.response_payload()

    def select_dashboard(self, dashboard_id: str) -> dict[str, Any]:
        if not any(dashboard["id"] == dashboard_id for dashboard in self.draft["dashboards"]):
            raise ValueError(f"Unknown dashboard: {dashboard_id}")
        self.selected_dashboard_id = dashboard_id
        return self.response_payload()

    def save(self) -> dict[str, Any]:
        normalized = normalize_dashboard_library_config(self.draft)
        normalized["active_dashboard_id"] = self.saved["active_dashboard_id"]
        normalized = normalize_dashboard_library_config(normalized)
        save_dashboard_library_config(normalized, self.config_path)
        self.saved = load_dashboard_library_config(self.config_path)
        self.draft = copy.deepcopy(self.saved)
        if not any(dashboard["id"] == self.selected_dashboard_id for dashboard in self.draft["dashboards"]):
            self.selected_dashboard_id = self.draft["active_dashboard_id"]
        return self.response_payload()

    def activate(self, dashboard_id: str) -> dict[str, Any]:
        if not any(dashboard["id"] == dashboard_id for dashboard in self.draft["dashboards"]):
            raise ValueError(f"Unknown dashboard: {dashboard_id}")
        self.draft["active_dashboard_id"] = dashboard_id
        save_dashboard_library_config(self.draft, self.config_path)
        self.saved = load_dashboard_library_config(self.config_path)
        self.draft = copy.deepcopy(self.saved)
        self.selected_dashboard_id = dashboard_id
        return self.response_payload()

    def render_preview(self, dashboard_id: str | None = None) -> bytes:
        self.preview_values.refresh_timestamps()
        dashboard_config = get_dashboard_by_id(self.draft, dashboard_id or self.selected_dashboard_id)
        dashboard = Dashboard(self.preview_values, config=dashboard_config)
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

    @app.post("/api/select/{dashboard_id}")
    def select_dashboard(dashboard_id: str) -> dict[str, Any]:
        try:
            return state.select_dashboard(dashboard_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.post("/api/activate/{dashboard_id}")
    def activate_dashboard(dashboard_id: str) -> dict[str, Any]:
        try:
            return state.activate(dashboard_id)
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

    @app.get("/api/dbcs")
    def dbcs() -> dict[str, Any]:
        return state.dbc_payload()

    @app.put("/api/dbcs/{interface}")
    async def put_dbc(interface: str, request: Request) -> dict[str, Any]:
        try:
            return state.replace_dbc(interface, await request.body())
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.get("/api/colors")
    def colors() -> dict[str, dict[str, list[int]]]:
        return {"colors": {name: list(value) for name, value in named_colors().items()}}

    @app.put("/api/mock-values")
    def mock_values(payload: dict[str, Any]) -> dict[str, Any]:
        state.update_preview_values(payload)
        return {"values": state.preview_values.get_snapshot()}

    @app.get("/api/preview.png")
    def preview(dashboard_id: str | None = None) -> Response:
        try:
            return Response(content=state.render_preview(dashboard_id), media_type="image/png")
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
