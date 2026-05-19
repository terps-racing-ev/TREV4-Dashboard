import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { FaFileExport, FaFileImport, FaRegCopy, FaRegSave, FaRegTrashAlt } from "react-icons/fa";
import "./styles.css";

const CANVAS = { width: 800, height: 480 };
const SNAP_OPTIONS = [0, 5, 10, 20, 40];

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail?.errors?.join(", ") || payload.errors?.join(", ") || response.statusText);
  }
  return response;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function makeDashboardId() {
  if (crypto.randomUUID) return `dash-${crypto.randomUUID()}`;
  return `dash-${Date.now()}-${Math.round(Math.random() * 100000)}`;
}

function defaultDashboard(name = "New Dashboard") {
  return {
    id: makeDashboardId(),
    name,
    display: { width: CANVAS.width, height: CANVAS.height, bg_color: [0, 0, 0] },
    gauges: [],
  };
}

function App() {
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(null);
  const [activeDashboardId, setActiveDashboardId] = useState(null);
  const [selectedDashboardId, setSelectedDashboardId] = useState(null);
  const [gaugeTypes, setGaugeTypes] = useState({});
  const [signals, setSignals] = useState([]);
  const [signalMetadata, setSignalMetadata] = useState({});
  const [colors, setColors] = useState({});
  const [dbcs, setDbcs] = useState({});
  const [selected, setSelected] = useState(0);
  const [warningsByDashboard, setWarningsByDashboard] = useState({});
  const [mockValues, setMockValues] = useState({});
  const [previewNonce, setPreviewNonce] = useState(Date.now());
  const [error, setError] = useState("");
  const [interaction, setInteraction] = useState(null);
  const [snapIndex, setSnapIndex] = useState(SNAP_OPTIONS.indexOf(20));
  const importRef = useRef(null);
  const dbcInputRefs = useRef({});
  const draftRef = useRef(null);
  const canvasRef = useRef(null);

  const dashboards = draft?.dashboards ?? [];
  const dashboard = dashboards.find((item) => item.id === selectedDashboardId) ?? dashboards[0];
  const dirty = useMemo(() => JSON.stringify(saved) !== JSON.stringify(draft), [saved, draft]);
  const gauge = dashboard?.gauges?.[selected];
  const snapSize = SNAP_OPTIONS[snapIndex];
  const warnings = dashboard ? warningsByDashboard[dashboard.id] ?? [] : [];

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    Promise.all([
      api("/api/config").then((r) => r.json()),
      api("/api/gauge-types").then((r) => r.json()),
      api("/api/signals").then((r) => r.json()),
      api("/api/colors").then((r) => r.json()),
      api("/api/dbcs").then((r) => r.json()),
    ])
      .then(([config, types, signalPayload, colorPayload, dbcPayload]) => {
        setSaved(config.saved);
        setDraft(config.draft);
        setActiveDashboardId(config.active_dashboard_id);
        setSelectedDashboardId(config.selected_dashboard_id);
        setWarningsByDashboard(config.validation.dashboards ?? {});
        setGaugeTypes(types);
        setSignals(signalPayload.signals);
        setSignalMetadata(signalPayload.metadata);
        setColors(colorPayload.colors);
        setDbcs(dbcPayload.dbcs);
        setMockValues(
          Object.fromEntries(
            Object.entries(signalPayload.metadata)
              .filter(([, metadata]) => metadata.choices.length > 0)
              .map(([name, metadata]) => [name, metadata.choices[0].value]),
          ),
        );
      })
      .catch((err) => setError(err.message));
  }, []);

  function applyConfigPayload(payload) {
    setSaved(payload.saved);
    setDraft(payload.draft);
    setActiveDashboardId(payload.active_dashboard_id);
    setSelectedDashboardId(payload.selected_dashboard_id);
    setWarningsByDashboard(payload.validation.dashboards ?? {});
    setPreviewNonce(Date.now());
  }

  async function pushDraft(next, { refreshPreview = true } = {}) {
    setDraft(next);
    const payload = await api("/api/draft", { method: "PUT", body: JSON.stringify(next) }).then((r) => r.json());
    setDraft(payload.draft);
    setActiveDashboardId(payload.active_dashboard_id);
    setSelectedDashboardId(payload.selected_dashboard_id);
    setWarningsByDashboard(payload.validation.dashboards ?? {});
    if (refreshPreview) setPreviewNonce(Date.now());
  }

  function updateSelectedDashboard(updater, options) {
    if (!dashboard) return;
    const next = clone(draft);
    const index = next.dashboards.findIndex((item) => item.id === dashboard.id);
    next.dashboards[index] = updater(next.dashboards[index]);
    pushDraft(next, options).catch((err) => setError(err.message));
  }

  async function selectDashboard(dashboardId) {
    setSelectedDashboardId(dashboardId);
    const nextDashboard = dashboards.find((item) => item.id === dashboardId);
    setSelected(nextDashboard?.gauges?.length > 0 ? 0 : null);
    const payload = await api(`/api/select/${encodeURIComponent(dashboardId)}`, { method: "POST" }).then((r) => r.json());
    setWarningsByDashboard(payload.validation.dashboards ?? {});
  }

  function renameDashboard(dashboardId, name) {
    const next = clone(draft);
    const item = next.dashboards.find((candidate) => candidate.id === dashboardId);
    if (!item) return;
    item.name = name;
    draftRef.current = next;
    setDraft(next);
  }

  function commitDashboardRename() {
    pushDraft(draftRef.current, { refreshPreview: false }).catch((err) => setError(err.message));
  }

  function addDashboard() {
    const next = clone(draft);
    const created = defaultDashboard(`Dashboard ${next.dashboards.length + 1}`);
    next.dashboards.push(created);
    setSelectedDashboardId(created.id);
    setSelected(null);
    pushDraft(next).catch((err) => setError(err.message));
  }

  function duplicateDashboard(dashboardId = dashboard?.id) {
    const sourceDashboard = dashboards.find((item) => item.id === dashboardId);
    if (!sourceDashboard) return;
    const next = clone(draft);
    const sourceIndex = next.dashboards.findIndex((item) => item.id === sourceDashboard.id);
    const copy = clone(next.dashboards[sourceIndex]);
    copy.id = makeDashboardId();
    copy.name = `${copy.name || "Dashboard"} Copy`;
    next.dashboards.splice(sourceIndex + 1, 0, copy);
    setSelectedDashboardId(copy.id);
    setSelected(copy.gauges.length > 0 ? 0 : null);
    pushDraft(next).catch((err) => setError(err.message));
  }

  function deleteDashboard(dashboardId) {
    if (dashboards.length <= 1) return;
    const next = clone(draft);
    const deleteIndex = next.dashboards.findIndex((item) => item.id === dashboardId);
    if (deleteIndex < 0) return;
    next.dashboards.splice(deleteIndex, 1);
    if (next.active_dashboard_id === dashboardId) {
      next.active_dashboard_id = next.dashboards[Math.max(0, deleteIndex - 1)].id;
    }
    const nextSelected = selectedDashboardId === dashboardId ? next.dashboards[Math.max(0, deleteIndex - 1)] : dashboard;
    setSelectedDashboardId(nextSelected.id);
    setSelected(nextSelected.gauges.length > 0 ? 0 : null);
    pushDraft(next).catch((err) => setError(err.message));
  }

  async function activateDashboard(dashboardId = dashboard?.id) {
    if (!dashboardId) return;
    const payload = await api(`/api/activate/${encodeURIComponent(dashboardId)}`, { method: "POST" }).then((r) => r.json());
    applyConfigPayload(payload);
  }

  function updateGauge(index, patch) {
    if (!dashboard || index == null) return;
    updateSelectedDashboard((item) => {
      item.gauges[index] = { ...item.gauges[index], ...patch };
      return item;
    });
  }

  function addGauge(type) {
    if (!dashboard) return;
    const fields = gaugeTypes[type].fields;
    const nextGauge = { type };
    fields.forEach((field) => {
      nextGauge[field.name] = clone(field.default);
    });
    nextGauge.box_xywh = [20 + dashboard.gauges.length * 12, 20 + dashboard.gauges.length * 12, 120, 80];
    updateSelectedDashboard((item) => {
      item.gauges.push(nextGauge);
      setSelected(item.gauges.length - 1);
      return item;
    });
  }

  function duplicateGauge() {
    if (!gauge) return;
    updateSelectedDashboard((item) => {
      const copy = clone(item.gauges[selected]);
      copy.box_xywh = [copy.box_xywh[0] + 12, copy.box_xywh[1] + 12, copy.box_xywh[2], copy.box_xywh[3]];
      item.gauges.splice(selected + 1, 0, copy);
      setSelected(selected + 1);
      return item;
    });
  }

  function deleteGauge() {
    if (!gauge) return;
    updateSelectedDashboard((item) => {
      item.gauges.splice(selected, 1);
      setSelected(item.gauges.length > 0 ? Math.max(0, selected - 1) : null);
      return item;
    });
  }

  async function save() {
    const payload = await api("/api/save", { method: "POST" }).then((r) => r.json());
    applyConfigPayload(payload);
  }

  async function importFile(file) {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const payload = await api("/api/import", { method: "POST", body: JSON.stringify(parsed) }).then((r) => r.json());
    setDraft(payload.draft);
    setActiveDashboardId(payload.active_dashboard_id);
    setSelectedDashboardId(payload.selected_dashboard_id);
    setWarningsByDashboard(payload.validation.dashboards ?? {});
    setSelected(0);
    setPreviewNonce(Date.now());
  }

  async function exportDraft() {
    const blob = await api("/api/export").then((r) => r.blob());
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "dashboard-config.json";
    link.click();
    URL.revokeObjectURL(href);
  }

  async function replaceDbc(interfaceName, file) {
    if (!file) return;
    const payload = await api(`/api/dbcs/${interfaceName}`, {
      method: "PUT",
      headers: { "Content-Type": "application/octet-stream" },
      body: await file.arrayBuffer(),
    }).then((r) => r.json());
    const signalPayload = await api("/api/signals").then((r) => r.json());
    setDbcs(payload.dbcs);
    setSignals(signalPayload.signals);
    setSignalMetadata(signalPayload.metadata);
    setMockValues(
      Object.fromEntries(
        Object.entries(signalPayload.metadata)
          .filter(([, metadata]) => metadata.choices.length > 0)
          .map(([name, metadata]) => [name, metadata.choices[0].value]),
      ),
    );
    setPreviewNonce(Date.now());
  }

  async function setMock(signal, value) {
    const next = { ...mockValues, [signal]: Number(value) };
    setMockValues(next);
    await api("/api/mock-values", { method: "PUT", body: JSON.stringify({ [signal]: Number(value) }) });
    setPreviewNonce(Date.now());
  }

  const gaugeSignalMetadata = gauge?.signal ? signalMetadata[gauge.signal] : null;

  function beginPointer(event, index, mode) {
    event.preventDefault();
    event.stopPropagation();
    const startRect = clone(dashboard.gauges[index].box_xywh);
    const scale = canvasRef.current ? canvasRef.current.clientWidth / CANVAS.width : 1;
    setSelected(index);
    setInteraction({ index, mode, startX: event.clientX, startY: event.clientY, rect: startRect, scale });
  }

  function snap(value) {
    return snapSize > 0 ? Math.round(value / snapSize) * snapSize : value;
  }

  useEffect(() => {
    if (!interaction || !dashboard) return;
    function onMove(event) {
      const dx = (event.clientX - interaction.startX) / interaction.scale;
      const dy = (event.clientY - interaction.startY) / interaction.scale;
      const [x, y, w, h] = interaction.rect;
      const box =
        interaction.mode === "resize"
          ? [
              x,
              y,
              Math.max(24, Math.min(CANVAS.width - x, snap(w + dx))),
              Math.max(24, Math.min(CANVAS.height - y, snap(h + dy))),
            ]
          : [
              Math.max(0, Math.min(CANVAS.width - w, snap(x + dx))),
              Math.max(0, Math.min(CANVAS.height - h, snap(y + dy))),
              w,
              h,
            ];
      const next = clone(draft);
      const dashboardIndex = next.dashboards.findIndex((item) => item.id === dashboard.id);
      next.dashboards[dashboardIndex].gauges[interaction.index].box_xywh = box;
      setDraft(next);
    }
    function onUp() {
      pushDraft(draftRef.current).catch((err) => setError(err.message));
      setInteraction(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [interaction, dashboard, draft]);

  useEffect(() => {
    function onKeyDown(event) {
      const target = event.target;
      const isEditing =
        target instanceof HTMLElement &&
        (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName));
      if (event.key === "Delete" && gauge && !isEditing) {
        event.preventDefault();
        deleteGauge();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [gauge, selected, draft]);

  if (!draft || !dashboard) return <main className="loading">Loading editor...</main>;

  return (
    <main className="shell">
      <header>
        <div>
          <h1>Dashboard Editor</h1>
          <span className={dirty ? "dirty" : "clean"}>{dirty ? "Unsaved changes" : "Saved"}</span>
        </div>
        <div className="dbc-center">
          {Object.entries(dbcs).map(([interfaceName, dbc]) => (
            <div className="dbc-pill" key={interfaceName}>
              <span>{interfaceName}: {dbc.filename}{dbc.fallback ? " (fallback)" : ""}</span>
              <button onClick={() => dbcInputRefs.current[interfaceName]?.click()}>Swap</button>
              <input
                ref={(node) => {
                  dbcInputRefs.current[interfaceName] = node;
                }}
                type="file"
                accept=".dbc"
                hidden
                onChange={(event) => replaceDbc(interfaceName, event.target.files[0]).catch((err) => setError(err.message))}
              />
            </div>
          ))}
        </div>
        <nav>
          <button onClick={save}><FaRegSave aria-hidden="true" /> Save</button>
          <button onClick={() => importRef.current.click()}><FaFileImport aria-hidden="true" /> Import</button>
          <button onClick={exportDraft}><FaFileExport aria-hidden="true" /> Export</button>
          <input ref={importRef} type="file" accept="application/json" hidden onChange={(e) => importFile(e.target.files[0])} />
        </nav>
      </header>

      {error && <div className="error">{error}</div>}
      {warnings.length > 0 && <div className="warnings">{warnings.map((item) => <div key={item}>{item}</div>)}</div>}

      <section className="workspace">
        <aside>
          <div className="row">
            <select className="add-gauge-select primary" onChange={(e) => addGauge(e.target.value)} value="">
              <option value="" disabled>Add gauge +</option>
              {Object.keys(gaugeTypes).map((type) => <option key={type}>{type}</option>)}
            </select>
          </div>
          <div className="gauge-list">
            {dashboard.gauges.map((item, index) => (
              <button key={`${item.type}-${index}`} className={index === selected ? "selected" : ""} onClick={() => setSelected(index)}>
                {index + 1}. {item.label || item.type}
              </button>
            ))}
          </div>
        </aside>

        <div className="preview-column">
          <div className="dashboard-strip" aria-label="Dashboards">
            {dashboards.map((item) => (
              <div
                key={item.id}
                role="button"
                tabIndex="0"
                className={`dashboard-tile ${item.id === dashboard.id ? "selected" : ""} ${item.id === activeDashboardId ? "active" : ""}`}
                onClick={() => selectDashboard(item.id).catch((err) => setError(err.message))}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectDashboard(item.id).catch((err) => setError(err.message));
                  }
                }}
              >
                <input
                  value={item.name}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => renameDashboard(item.id, event.target.value)}
                  onBlur={commitDashboardRename}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                />
                <span className="thumbnail-wrap">
                  <img src={`/api/preview.png?dashboard_id=${encodeURIComponent(item.id)}&t=${previewNonce}`} width="160" height="96" />
                  {item.id === activeDashboardId && <span className="active-badge">Active</span>}
                </span>
                <span className="dashboard-actions">
                  {item.id === activeDashboardId ? (
                    <span className="active-label">Active</span>
                  ) : (
                    <button
                      className="set-active-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        activateDashboard(item.id).catch((err) => setError(err.message));
                      }}
                    >
                      Set active
                    </button>
                  )}
                  <button
                    className="icon-button"
                    title="Duplicate dashboard"
                    aria-label={`Duplicate ${item.name}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      duplicateDashboard(item.id);
                    }}
                  >
                    <FaRegCopy aria-hidden="true" />
                  </button>
                  <button
                    className="icon-button danger"
                    title="Delete dashboard"
                    aria-label={`Delete ${item.name}`}
                    disabled={dashboards.length <= 1 || item.id === activeDashboardId}
                    onClick={(event) => {
                      event.stopPropagation();
                      deleteDashboard(item.id);
                    }}
                  >
                    <FaRegTrashAlt aria-hidden="true" />
                  </button>
                </span>
              </div>
            ))}
            <button className="dashboard-tile add-dashboard" onClick={addDashboard}>
              <span className="plus">+</span>
            </button>
          </div>

          <div className="preview-toolbar">
            <div className="row actions">
              <button className="icon-button toolbar-icon" onClick={duplicateGauge} disabled={!gauge} title="Duplicate gauge" aria-label="Duplicate gauge">
                <FaRegCopy aria-hidden="true" />
              </button>
              <button className="icon-button toolbar-icon danger" onClick={deleteGauge} disabled={!gauge} title="Delete gauge" aria-label="Delete gauge">
                <FaRegTrashAlt aria-hidden="true" />
              </button>
            </div>
          </div>
          <div
            ref={canvasRef}
            className={`canvas ${snapSize > 0 ? "with-grid" : ""}`}
            style={{
              "--grid-size-x": `${(snapSize / CANVAS.width) * 100}%`,
              "--grid-size-y": `${(snapSize / CANVAS.height) * 100}%`,
            }}
            onPointerDown={() => setSelected(null)}
          >
            <img src={`/api/preview.png?dashboard_id=${encodeURIComponent(dashboard.id)}&t=${previewNonce}`} width="800" height="480" />
            {dashboard.gauges.map((item, index) => {
              const [x, y, w, h] = item.box_xywh;
              return (
                <div
                  key={index}
                  className={`overlay ${index === selected ? "selected" : ""}`}
                  style={{
                    left: `${(x / CANVAS.width) * 100}%`,
                    top: `${(y / CANVAS.height) * 100}%`,
                    width: `${(w / CANVAS.width) * 100}%`,
                    height: `${(h / CANVAS.height) * 100}%`,
                  }}
                  onPointerDown={(event) => beginPointer(event, index, "move")}
                >
                  {index === selected && <span onPointerDown={(event) => beginPointer(event, index, "resize")} />}
                </div>
              );
            })}
          </div>
          <div className="snap-controls">
            <button onClick={() => setSnapIndex((current) => (current + 1) % SNAP_OPTIONS.length)}>
              Snap: {snapSize === 0 ? "None" : `${snapSize}px`}
            </button>
          </div>
        </div>

        <aside className="inspector">
          <h2>{gauge?.type || "No gauge selected"}</h2>
          {gauge?.signal && (
            <div className="preview-value-block">
              <label>
                <span>Preview value</span>
                {gaugeSignalMetadata?.choices?.length > 0 ? (
                  <select
                    value={mockValues[gauge.signal] ?? gaugeSignalMetadata.choices[0].value}
                    onChange={(event) => setMock(gauge.signal, event.target.value)}
                  >
                    {gaugeSignalMetadata.choices.map((choice) => (
                      <option key={choice.value} value={choice.value}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    value={mockValues[gauge.signal] ?? 0}
                    onChange={(event) => setMock(gauge.signal, event.target.value)}
                  />
                )}
              </label>
            </div>
          )}
          {gauge &&
            gaugeTypes[gauge.type].fields.map((field) => (
              <label key={field.name}>
                <span>{field.label}</span>
                <FieldInput
                  field={field}
                  value={gauge[field.name]}
                  signals={signals}
                  colors={colors}
                  onChange={(value) => updateGauge(selected, { [field.name]: value })}
                />
              </label>
            ))}
        </aside>
      </section>
    </main>
  );
}

function FieldInput({ field, value, signals, colors, onChange }) {
  if (field.kind === "signal") {
    return (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">-</option>
        {signals.map((signal) => <option key={signal}>{signal}</option>)}
      </select>
    );
  }
  if (field.kind === "bool") {
    return <input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />;
  }
  if (field.kind === "rect") {
    return (
      <input
        value={value.join(", ")}
        onChange={(event) => onChange(event.target.value.split(",").map((part) => Number(part.trim())))}
      />
    );
  }
  if (field.kind === "color") {
    const currentName =
      typeof value === "string"
        ? value
        : Object.entries(colors).find(([, rgb]) => JSON.stringify(rgb) === JSON.stringify(value))?.[0] ?? "";
    return (
      <select value={value == null ? "__none__" : currentName} onChange={(event) => onChange(event.target.value === "__none__" ? null : event.target.value)}>
        <option value="__none__">None</option>
        {Object.keys(colors).map((name) => <option key={name}>{name}</option>)}
      </select>
    );
  }
  return (
    <input
      type={field.kind === "number" || field.kind === "int" ? "number" : "text"}
      value={value}
      onChange={(event) => onChange(field.kind === "number" || field.kind === "int" ? Number(event.target.value) : event.target.value)}
    />
  );
}

createRoot(document.getElementById("root")).render(<App />);
