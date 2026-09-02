import { useEffect, useState, type ChangeEvent } from "react";
import { api, ApiError } from "../api/client";
import type { QueryBackend, QueryResult } from "../types";

const TEMPLATE: Record<string, string> = {
  neo4j: "MATCH (n) RETURN labels(n) AS label, count(*) AS count\nORDER BY count DESC\nLIMIT 10",
  mork: ";; MeTTa read-only query (e.g.)",
};

export default function QueryPage() {
  const [backends, setBackends] = useState<QueryBackend[]>([]);
  const [backend, setBackend] = useState<string>("neo4j");
  const [query, setQuery] = useState<string>("");
  const [limit, setLimit] = useState<number>(200);
  const [timeoutMs, setTimeoutMs] = useState<number>(10000);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [writeBlocked, setWriteBlocked] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listQueryBackends()
      .then((b) => {
        setBackends(b);
        if (b.length) setBackend(b[0].name);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  function useTemplate(e: ChangeEvent<HTMLSelectElement>) {
    const b = e.target.value;
    setBackend(b);
    setQuery((prev) => prev || TEMPLATE[b] || "");
  }

  async function onRun() {
    setRunning(true);
    setError(null);
    setWriteBlocked(false);
    setResult(null);
    try {
      const r = await api.runQuery(backend, query, limit, timeoutMs);
      setResult(r);
    } catch (e) {
      if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
        const d = e.detail as { message?: string; write_blocked?: boolean };
        setError(d.message ?? String(e));
        setWriteBlocked(!!d.write_blocked);
      } else {
        setError(String(e));
      }
    } finally {
      setRunning(false);
    }
  }

  const current = backends.find((b) => b.name === backend);

  return (
    <div>
      <div className="card">
        <h2>
          <span className="step">Q</span> Read-only query explorer
        </h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <label className="field">
            Backend
            <select value={backend} onChange={useTemplate}>
              {backends.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.display_name}
                  {b.available ? " (connected)" : " (offline)"}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Max rows
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {[50, 100, 200, 500, 1000, 2000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Timeout (ms)
            <select
              value={timeoutMs}
              onChange={(e) => setTimeoutMs(Number(e.target.value))}
            >
              {[5000, 10000, 30000, 60000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field-hint" style={{ marginBottom: 10 }}>
          Query in{" "}
          <span className="mono">{current?.query_language ?? "?"}</span>. Results are
          read-only — any attempt to modify the live graph is blocked.
        </div>
        <textarea
          className="query-editor"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          // role="textbox" is implied; spellCheck off for query languages
          spellCheck={false}
          placeholder={`Enter a ${current?.query_language ?? ""} query…`}
        />
        <div className="row" style={{ marginTop: 12 }}>
          <button
            className="primary"
            onClick={onRun}
            disabled={running || !query.trim()}
          >
            {running ? "Running…" : "Run query"}
          </button>
          {!current?.available && (
            <span className="muted" style={{ fontSize: 12 }}>
              Backend unreachable — queries will fail until it's online.
            </span>
          )}
        </div>
        {loadError && <div className="alert err">{loadError}</div>}
      </div>

      {writeBlocked && (
        <div className="alert err">
          ⛔ <strong>Blocked:</strong> {error}
        </div>
      )}
      {error && !writeBlocked && <div className="alert err">{error}</div>}

      {result && (
        <ResultTable result={result} />
      )}
    </div>
  );
}

function ResultTable({ result }: { result: QueryResult }) {
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ marginBottom: 0 }}>
          Results{" "}
          <span className="muted mono">
            {result.returned}/{result.row_count} rows · {result.elapsed_ms} ms
          </span>
        </h2>
        {result.truncated && (
          <span className="tag node">truncated</span>
        )}
      </div>
      {result.rows.length === 0 ? (
        <div className="muted">No rows returned.</div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {result.fields.map((f) => (
                  <th key={f}>{f}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{renderCell(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
