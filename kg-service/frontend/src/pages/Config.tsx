import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ConfigFileInfo, ConfigValidation } from "../types";

const KIND_LABEL: Record<string, string> = {
  adapters: "Adapters",
  schema: "Schema",
  species: "Species registry",
  other: "Other",
};

export default function ConfigPage() {
  const [files, setFiles] = useState<ConfigFileInfo[]>([]);
  const [path, setPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [origContent, setOrigContent] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fileMeta, setFileMeta] = useState<{ path: string; size: number } | null>(null);

  const [validation, setValidation] = useState<ConfigValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const grouped = useMemo(() => {
    const order = ["adapters", "schema", "species", "other"];
    const map: Record<string, ConfigFileInfo[]> = { adapters: [], schema: [], species: [], other: [] };
    files.forEach((f) => {
      const key = f.kind in map ? f.kind : "other";
      map[key].push(f);
    });
    return order.map((k) => ({ kind: k, items: map[k] ?? [] })).filter((g) => g.items.length);
  }, [files]);

  useEffect(() => {
    api
      .listConfigFiles()
      .then((f) => setFiles(f))
      .catch((e) => setLoadError(String(e)));
  }, []);

  async function selectFile(p: string) {
    setPath(p);
    setValidation(null);
    setSaveMsg(null);
    try {
      const f = await api.getConfigFile(p);
      setContent(f.content);
      setOrigContent(f.content);
      setFileMeta({ path: f.relative_path, size: f.size });
    } catch (e) {
      setLoadError(String(e));
    }
  }

  const dirty = content !== origContent;

  async function onValidate() {
    setValidating(true);
    setSaveMsg(null);
    try {
      setValidation(await api.validateConfigFile(path, content));
    } catch (e) {
      const err = e instanceof ApiError && e.detail && typeof e.detail === "object"
        ? ((e.detail as { message?: string }).message ?? String(e))
        : String(e);
      setSaveMsg({ type: "err", text: err });
      setValidation(null);
    } finally {
      setValidating(false);
    }
  }

  async function onSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await api.saveConfigFile(path, content);
      setSaveMsg({
        type: "ok",
        text: res.backup
          ? `Saved. Backup kept at ${res.backup}.`
          : "Saved successfully.",
      });
      setOrigContent(content);
      setValidation(res.validation);
      setFileMeta((m) => (m ? { ...m, size: content.length } : m));
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const d = e.detail as { message?: string; validation?: ConfigValidation };
        setValidation(d.validation ?? null);
        setSaveMsg({ type: "err", text: d.message ?? String(e) });
      } else {
        const err = e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? ((e.detail as { message?: string }).message ?? String(e))
          : String(e);
        setSaveMsg({ type: "err", text: err });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="card">
        <h2>
          <span className="step">3</span> Inline configuration editor
        </h2>
        <div className="field-hint" style={{ marginBottom: 12 }}>
          Edit adapters, schema, and data-source configs directly in the Console.
          Every save is validated and the previous version is backed up — a bad
          config can never corrupt a live file.
        </div>
        {loadError && <div className="alert err">{loadError}</div>}
        <div className="cfg-layout">
          <div className="cfg-tree">
            {grouped.map((g) => (
              <div key={g.kind} className="cfg-group">
                <div className="group-head">
                  <span className={`group-dot ${g.kind === "adapters" ? "node" : g.kind === "schema" ? "edge" : ""}`} />
                  <span className="group-title">{KIND_LABEL[g.kind]}</span>
                </div>
                {g.items.map((f) => (
                  <button
                    key={f.path}
                    className={`cfg-file ${f.path === path ? "active" : ""}`}
                    onClick={() => selectFile(f.path)}
                    title={f.path}
                  >
                    {f.name}
                  </button>
                ))}
              </div>
            ))}
            {!files.length && <div className="muted">No editable config files found.</div>}
          </div>

          <div className="cfg-editor">
            {!path ? (
              <div className="muted">Select a config file on the left to begin.</div>
            ) : (
              <>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                  <span className="mono muted">{fileMeta?.path}</span>
                  {dirty && <span className="tag node">unsaved changes</span>}
                </div>
                <textarea
                  className="cfg-textarea"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  spellCheck={false}
                />
                <div className="row" style={{ marginTop: 12 }}>
                  <button
                    className="secondary"
                    onClick={onValidate}
                    disabled={validating}
                  >
                    {validating ? "Validating…" : "Validate"}
                  </button>
                  <button
                    className="primary"
                    onClick={onSave}
                    disabled={saving || !dirty}
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  {!dirty && (
                    <span className="muted" style={{ fontSize: 12 }}>
                      No changes to save.
                    </span>
                  )}
                </div>

                {validation && (
                  <ValidationFeedback v={validation} />
                )}
                {saveMsg && (
                  <div className={`alert ${saveMsg.type}`}>{saveMsg.text}</div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ValidationFeedback({ v }: { v: ConfigValidation }) {
  return (
    <div style={{ marginTop: 14 }}>
      {v.valid ? (
        <div className="alert ok">
          ✓ Valid{v.existing ? "" : " (new file)"}
          {v.summary && (
            <span className="muted" style={{ marginLeft: 8 }}>
              {summarize(v.summary)}
            </span>
          )}
        </div>
      ) : (
        <div className="alert err">✗ Not valid — fix the errors below</div>
      )}
      {v.errors.map((e, i) => (
        <div className="alert err" key={`e${i}`}>
          {e}
        </div>
      ))}
      {v.warnings.map((w, i) => (
        <div className="alert warn" key={`w${i}`}>
          ⚠ {w}
        </div>
      ))}
    </div>
  );
}

function summarize(s: Record<string, unknown>): string {
  const adapters = s.adapters;
  const nodes = Array.isArray(s.node_types) ? (s.node_types as string[]).length : undefined;
  const edges = Array.isArray(s.edge_types) ? (s.edge_types as string[]).length : undefined;
  if (adapters != null) return `(${adapters} adapters)`;
  if (nodes != null && edges != null) return `(${nodes} node / ${edges} edge types)`;
  if (s.species_count != null) return `(${s.species_count} species)`;
  return "";
}
