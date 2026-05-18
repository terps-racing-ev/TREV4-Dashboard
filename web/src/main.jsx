import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
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

function App() {
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(null);
  const [gaugeTypes, setGaugeTypes] = useState({});
  const [signals, setSignals] = useState([]);
  const [signalMetadata, setSignalMetadata] = useState({});
  const [colors, setColors] = useState({});
  const [selected, setSelected] = useState(0);
  const [warnings, setWarnings] = useState([]);
  const [mockValues, setMockValues] = useState({});
  const [previewNonce, setPreviewNonce] = useState(Date.now());
  const [error, setError] = useState("");
  const [interaction, setInteraction] = useState(null);
  const [snapIndex, setSnapIndex] = useState(0);
  const importRef = useRef(null);
  const draftRef = useRef(null);
  const canvasRef = useRef(null);

  const dirty = useMemo(() => JSON.stringify(saved) !== JSON.stringify(draft), [saved, draft]);
  const gauge = draft?.gauges?.[selected];
  const snapSize = SNAP_OPTIONS[snapIndex];

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    Promise.all([
      api("/api/config").then((r) => r.json()),
      api("/api/gauge-types").then((r) => r.json()),
      api("/api/signals").then((r) => r.json()),
      api("/api/colors").then((r) => r.json()),
    ])
      .then(([config, types, signalPayload, colorPayload]) => {
        setSaved(config.saved);
        setDraft(config.draft);
        setWarnings(config.validation.warnings);
        setGaugeTypes(types);
        setSignals(signalPayload.signals);
        setSignalMetadata(signalPayload.metadata);
        setColors(colorPayload.colors);
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

  async function pushDraft(next) {
    setDraft(next);
    const payload = await api("/api/draft", { method: "PUT", body: JSON.stringify(next) }).then((r) => r.json());
    setDraft(payload.draft);
    setWarnings(payload.validation.warnings);
    setPreviewNonce(Date.now());
  }

  function updateGauge(index, patch) {
    const next = clone(draft);
    next.gauges[index] = { ...next.gauges[index], ...patch };
    pushDraft(next).catch((err) => setError(err.message));
  }

  function addGauge(type) {
    const fields = gaugeTypes[type].fields;
    const nextGauge = { type };
    fields.forEach((field) => {
      nextGauge[field.name] = clone(field.default);
    });
    nextGauge.box_xywh = [20 + draft.gauges.length * 12, 20 + draft.gauges.length * 12, 120, 80];
    const next = clone(draft);
    next.gauges.push(nextGauge);
    setSelected(next.gauges.length - 1);
    pushDraft(next).catch((err) => setError(err.message));
  }

  function duplicateGauge() {
    if (!gauge) return;
    const next = clone(draft);
    const copy = clone(next.gauges[selected]);
    copy.box_xywh = [copy.box_xywh[0] + 12, copy.box_xywh[1] + 12, copy.box_xywh[2], copy.box_xywh[3]];
    next.gauges.splice(selected + 1, 0, copy);
    setSelected(selected + 1);
    pushDraft(next).catch((err) => setError(err.message));
  }

  function deleteGauge() {
    if (!gauge) return;
    const next = clone(draft);
    next.gauges.splice(selected, 1);
    setSelected(next.gauges.length > 0 ? Math.max(0, selected - 1) : null);
    pushDraft(next).catch((err) => setError(err.message));
  }

  function moveGauge(direction) {
    if (!gauge) return;
    const target = selected + direction;
    if (target < 0 || target >= draft.gauges.length) return;
    const next = clone(draft);
    [next.gauges[selected], next.gauges[target]] = [next.gauges[target], next.gauges[selected]];
    setSelected(target);
    pushDraft(next).catch((err) => setError(err.message));
  }

  async function save() {
    const payload = await api("/api/save", { method: "POST" }).then((r) => r.json());
    setSaved(payload.saved);
    setDraft(payload.draft);
    setWarnings(payload.validation.warnings);
    setPreviewNonce(Date.now());
  }

  async function importFile(file) {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const payload = await api("/api/import", { method: "POST", body: JSON.stringify(parsed) }).then((r) => r.json());
    setDraft(payload.draft);
    setWarnings(payload.validation.warnings);
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
    const startRect = clone(draft.gauges[index].box_xywh);
    const scale = canvasRef.current ? canvasRef.current.clientWidth / CANVAS.width : 1;
    setSelected(index);
    setInteraction({ index, mode, startX: event.clientX, startY: event.clientY, rect: startRect, scale });
  }

  function snap(value) {
    return snapSize > 0 ? Math.round(value / snapSize) * snapSize : value;
  }

  useEffect(() => {
    if (!interaction) return;
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
      next.gauges[interaction.index].box_xywh = box;
      setDraft(next);
    }
    function onUp() {
      pushDraft(draftRef.current).catch((err) => setError(err.message));
      setInteraction(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [interaction]);

  if (!draft) return <main className="loading">Loading editor…</main>;

  return (
    <main className="shell">
      <header>
        <div>
          <h1>Dashboard Editor</h1>
          <span className={dirty ? "dirty" : "clean"}>{dirty ? "Unsaved changes" : "Saved"}</span>
        </div>
        <nav>
          <button onClick={save}>Save</button>
          <button onClick={() => importRef.current.click()}>Import</button>
          <button onClick={exportDraft}>Export</button>
          <input ref={importRef} type="file" accept="application/json" hidden onChange={(e) => importFile(e.target.files[0])} />
        </nav>
      </header>

      {error && <div className="error">{error}</div>}
      {warnings.length > 0 && <div className="warnings">{warnings.map((item) => <div key={item}>{item}</div>)}</div>}

      <section className="workspace">
        <aside>
          <div className="row">
            <select onChange={(e) => addGauge(e.target.value)} value="">
              <option value="" disabled>Add gauge…</option>
              {Object.keys(gaugeTypes).map((type) => <option key={type}>{type}</option>)}
            </select>
          </div>
          <div className="gauge-list">
            {draft.gauges.map((item, index) => (
              <button key={`${item.type}-${index}`} className={index === selected ? "selected" : ""} onClick={() => setSelected(index)}>
                {index + 1}. {item.label || item.type}
              </button>
            ))}
          </div>
          <div className="row actions">
            <button onClick={duplicateGauge} disabled={!gauge}>Duplicate</button>
            <button onClick={deleteGauge} disabled={!gauge}>Delete</button>
            <button onClick={() => moveGauge(-1)} disabled={!gauge || selected === 0}>↑</button>
            <button onClick={() => moveGauge(1)} disabled={!gauge || selected === draft.gauges.length - 1}>↓</button>
          </div>
        </aside>

        <div className="preview-column">
          <div
            ref={canvasRef}
            className={`canvas ${snapSize > 0 ? "with-grid" : ""}`}
            style={{
              "--grid-size-x": `${(snapSize / CANVAS.width) * 100}%`,
              "--grid-size-y": `${(snapSize / CANVAS.height) * 100}%`,
            }}
            onPointerDown={() => setSelected(null)}
          >
            <img src={`/api/preview.png?t=${previewNonce}`} width="800" height="480" />
            {draft.gauges.map((item, index) => {
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
          {gauge?.signal && (
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
          )}
        </aside>
      </section>
    </main>
  );
}

function FieldInput({ field, value, signals, colors, onChange }) {
  if (field.kind === "signal") {
    return (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">—</option>
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
