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

from app.dashboard import Dashboard
from app.dbc_utils import (
    load_dbc_catalog,
    load_signal_metadata,
    relative_dbc_path,
    reserve_dbc_upload_path,
    resolve_active_dbc_paths,
    save_dbc_catalog,
    sort_dbc_entries,
)
from app.gauge_config import (
    GAUGE_SPECS,
    get_dashboard_by_id,
    load_dashboard_library_config,
    normalize_dashboard_library_config,
    save_dashboard_library_config,
    validate_layout,
)
from app.lap_timer import lap_timer_signal_metadata
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

    def dbc_catalog(self) -> dict[str, list[dict[str, Any]]]:
        return load_dbc_catalog(CONFIG_DIR, CAN_INTERFACES)

    def active_dbc_paths(self) -> dict[str, list[Path]]:
        return resolve_active_dbc_paths(CONFIG_DIR, CAN_INTERFACES)

    def dbc_payload(self) -> dict[str, Any]:
        catalog = self.dbc_catalog()
        return {
            "dbcs": {
                interface: {
                    "files": [
                        {
                            "id": entry["path"],
                            "filename": Path(entry["path"]).name,
                            "enabled": bool(entry.get("enabled", True)),
                            "priority": int(entry.get("priority", 0)),
                            "missing": not (CONFIG_DIR / entry["path"]).exists(),
                            "active": bool(entry.get("enabled", True)) and (CONFIG_DIR / entry["path"]).exists(),
                        }
                        for entry in sort_dbc_entries(catalog.get(interface, []))
                    ],
                }
                for interface in CAN_INTERFACES
            }
        }

    def reload_signal_metadata(self) -> None:
        self.signal_metadata = load_signal_metadata(self.active_dbc_paths())
        self.signal_metadata.update(lap_timer_signal_metadata(self.draft.get("lap_timer")))
        self.signal_metadata = dict(sorted(self.signal_metadata.items()))
        self.signal_names = list(self.signal_metadata)

    def _refresh_after_dbc_change(self) -> None:
        self.preview_values.clear()
        self.reload_signal_metadata()
        self._seed_enum_preview_values()

    def replace_dbc(self, interface: str, filename: str, content: bytes) -> dict[str, Any]:
        if interface not in CAN_INTERFACES:
            raise ValueError(f"Unknown interface: {interface}")
        if not content:
            raise ValueError("DBC upload is empty")

        catalog = self.dbc_catalog()
        uploaded_stem = Path(filename).stem.strip()

        # Check if a DBC with the same base name already exists in the catalog
        existing_entry = None
        for entry in catalog[interface]:
            if Path(entry["path"]).stem == uploaded_stem:
                existing_entry = entry
                break

        if existing_entry is not None:
            # Overwrite the existing file in-place
            target = CONFIG_DIR / existing_entry["path"]
        else:
            target = reserve_dbc_upload_path(CONFIG_DIR, interface, filename)

        temp_target = target.with_suffix(".dbc.tmp")
        temp_target.write_bytes(content)
        temp_target.replace(target)

        if existing_entry is None:
            # Only append a new catalog entry if this is a new file
            catalog[interface].append(
                {
                    "path": relative_dbc_path(CONFIG_DIR, target),
                    "enabled": True,
                    "priority": max((int(entry.get("priority", 0)) for entry in catalog[interface]), default=-1) + 1,
                }
            )
        catalog[interface] = sort_dbc_entries(catalog[interface])
        save_dbc_catalog(CONFIG_DIR, catalog, CAN_INTERFACES)
        self._refresh_after_dbc_change()
        return self.dbc_payload()

    def delete_dbc(self, interface: str, file_id: str) -> dict[str, Any]:
        if interface not in CAN_INTERFACES:
            raise ValueError(f"Unknown interface: {interface}")

        catalog = self.dbc_catalog()
        original_len = len(catalog[interface])
        catalog[interface] = [
            entry for entry in catalog[interface] if entry["path"] != file_id
        ]
        if len(catalog[interface]) == original_len:
            raise ValueError(f"Unknown DBC entry: {file_id}")

        # Optionally remove the file from disk
        file_path = CONFIG_DIR / file_id
        if file_path.exists():
            file_path.unlink()

        catalog[interface] = sort_dbc_entries(catalog[interface])
        save_dbc_catalog(CONFIG_DIR, catalog, CAN_INTERFACES)
        self._refresh_after_dbc_change()
        return self.dbc_payload()

    def update_dbc_catalog(self, interface: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        if interface not in CAN_INTERFACES:
            raise ValueError(f"Unknown interface: {interface}")

        catalog = self.dbc_catalog()
        existing = {entry["path"]: dict(entry) for entry in catalog[interface]}
        seen: set[str] = set()
        next_entries: list[dict[str, Any]] = []

        for item in files:
            entry_id = str(item.get("id", "")).strip()
            if not entry_id or entry_id not in existing:
                raise ValueError(f"Unknown DBC entry: {entry_id}")
            if entry_id in seen:
                raise ValueError(f"Duplicate DBC entry: {entry_id}")
            seen.add(entry_id)
            current = existing[entry_id]
            current["enabled"] = bool(item.get("enabled", current.get("enabled", True)))
            current["priority"] = int(item.get("priority", current.get("priority", 0)))
            next_entries.append(current)

        next_entries.extend(entry for path, entry in existing.items() if path not in seen)
        catalog[interface] = sort_dbc_entries(next_entries)
        save_dbc_catalog(CONFIG_DIR, catalog, CAN_INTERFACES)
        self._refresh_after_dbc_change()
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
        for name in lap_timer_signal_metadata(self.draft.get("lap_timer")):
            raw_values.setdefault(name, 0)
            display_values.setdefault(name, 0)
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
        self.reload_signal_metadata()
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
            filename = request.headers.get("x-file-name", f"{interface}.dbc")
            return state.replace_dbc(interface, filename, await request.body())
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.delete("/api/dbcs/{interface}/{file_path:path}")
    def delete_dbc(interface: str, file_path: str) -> dict[str, Any]:
        try:
            return state.delete_dbc(interface, file_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

    @app.put("/api/dbcs/{interface}/catalog")
    def put_dbc_catalog(interface: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return state.update_dbc_catalog(interface, payload.get("files", []))
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"errors": [str(exc)], "warnings": []}) from exc

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
