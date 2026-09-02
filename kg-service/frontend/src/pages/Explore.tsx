import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BrowserOverview, BrowserDataset, VersionEntry } from "../types";

const MAX_GRAPH_NODES = 60;

export default function ExplorePage() {
  const [data, setData] = useState<BrowserOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .browserOverview()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <div className="muted">Loading graph metadata…</div>;
  if (error) return <div className="alert err">{error}</div>;
  if (!data) return null;

  const { overview, distributions, schema, detailed_schema, datasets, versions } = data;

  return (
    <div>
      <div className="card">
        <h2>
          <span className="step">2</span> Graph overview
        </h2>
        <div className="stat-grid">
          <Stat label="Nodes" value={fmtInt(overview.node_count)} />
          <Stat label="Edges" value={fmtInt(overview.edge_count)} />
          <Stat label="Datasets" value={fmtInt(overview.dataset_count)} />
          <Stat label="Last updated" value={overview.last_updated_at?.slice(0, 10) ?? "—"} />
          <Stat label="Store size" value={overview.database_size_gb != null ? `${overview.database_size_gb} GB` : "—"} />
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <span className={`loadpill ${data.neo4j_connected ? "ok" : "err"}`}>
            Neo4j {data.neo4j_connected ? "connected" : "offline"}
          </span>
          <span className={`loadpill ${data.mork_connected ? "ok" : "err"}`}>
            MORK {data.mork_connected ? "connected" : "offline"}
          </span>
        </div>
      </div>

      <div className="card">
        <h2>Entity &amp; relationship distribution</h2>
        <div className="dist-grid">
          <DistPanel
            title="Top node types"
            items={distributions.node_types}
            accent="teal"
          />
          <DistPanel
            title="Top relationship types"
            items={distributions.edge_types}
            accent="cyan"
          />
        </div>
      </div>

      <div className="card">
        <h2>Schema browser</h2>
        <SchemaGraph
          nodes={detailed_schema.nodes.map((n) => n.data)}
          edges={detailed_schema.edges.map((e) => e.data)}
        />
        <div className="row" style={{ marginTop: 14, gap: 22 }}>
          <ChipColumn title="Node types" items={schema.node_types} />
          <ChipColumn title="Relationship types" items={schema.relationship_types} />
        </div>
      </div>

      <DatasetsCard datasets={datasets} />

      <div className="card">
        <h2>Dataset versions</h2>
        <div className="dist-grid">
          <VersionsPanel title="Neo4j versions" versions={versions.neo4j} />
          <VersionsPanel title="MORK versions" morkVersions={versions.mork} />
        </div>
      </div>
    </div>
  );
}

function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString();
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function DistPanel({
  title,
  items,
  accent,
}: {
  title: string;
  items: { name: string; count: number }[];
  accent: "teal" | "cyan";
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <div>
      <h3 className="panel-title">{title}</h3>
      {!items.length && <div className="muted">No data.</div>}
      <div className="dist-list">
        {items.map((i) => (
          <div className="dist-row" key={i.name}>
            <span className="dist-name" title={i.name}>
              {i.name}
            </span>
            <div className="dist-track">
              <div
                className={`dist-fill ${accent}`}
                style={{ width: `${(i.count / max) * 100}%` }}
              />
            </div>
            <span className="dist-count">{i.count.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

type SchemaNode = { id: string; properties: string[] };
type SchemaEdge = {
  source: string;
  target: string;
  possible_connections: string[];
};

function SchemaGraph({
  nodes,
  edges,
}: {
  nodes: SchemaNode[];
  edges: SchemaEdge[];
}) {
  const [selected, setSelected] = useState<string | null>(null);

  if (nodes.length > MAX_GRAPH_NODES) {
    return (
      <div className="alert warn">
        Too many node types ({nodes.length}) to render as a graph — using tables.
      </div>
    );
  }

  if (!nodes.length) {
    return <div className="muted">No schema loaded (graph offline).</div>;
  }

  const n = nodes.length;
  const cx = 420;
  const cy = 260;
  const R = Math.min(200, 60 + n * 9);
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[node.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  });

  const connectedIds = new Set<string>();
  edges.forEach((e) => {
    connectedIds.add(e.source);
    connectedIds.add(e.target);
  });

  const selectNode = (id: string) =>
    setSelected((prev) => (prev === id ? null : id));

  return (
    <div>
      <svg viewBox="0 0 840 520" className="schema-svg">
        {edges
          .filter(
            (e) =>
              (!selected ||
                e.source === selected ||
                e.target === selected) &&
              pos[e.source] &&
              pos[e.target],
          )
          .map((e, i) => {
            const from = pos[e.source];
            const to = pos[e.target];
            const active = selected && (e.source === selected || e.target === selected);
            return (
              <line
                key={i}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className={active ? "schema-edge active" : "schema-edge"}
              />
            );
          })}
        {nodes.map((node) => {
          const p = pos[node.id];
          const isSelected = selected === node.id;
          const isConnected = node.id === selected || (selected && connectedIds.has(node.id) &&
            edges.some((e) => (e.source === selected || e.target === selected) &&
              (e.source === node.id || e.target === node.id)));
          return (
            <g
              key={node.id}
              className="schema-node"
              onClick={() => selectNode(node.id)}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={isSelected ? 22 : 13}
                className={`schema-node-circle ${isSelected ? "active" : ""} ${
                  selected && !isConnected && node.id !== selected ? "dim" : ""
                }`}
              />
              <text x={p.x} y={p.y + 4} textAnchor="middle" className="schema-node-label">
                {short(node.id, selected === node.id ? 24 : 12)}
              </text>
            </g>
          );
        })}
      </svg>
      {selected ? (
        <div className="card node-detail">
          <button className="linkbtn" onClick={() => setSelected(null)}>
            ✕ clear selection
          </button>
          <h3 className="mono" style={{ margin: "6px 0" }}>
            {selected}
          </h3>
          <div className="row" style={{ gap: 6 }}>
            <ChipColumn title="Properties" items={nodeProps(nodes, selected)} />
            <ChipColumn
              title="Relationships"
              items={relatedEdges(edges, selected)}
            />
          </div>
        </div>
      ) : (
        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          Click a node to inspect its properties and relationships.
        </div>
      )}
    </div>
  );
}

function nodeProps(nodes: SchemaNode[], id: string): string[] {
  return nodes.find((n) => n.id === id)?.properties ?? [];
}

function relatedEdges(
  edges: SchemaEdge[],
  id: string,
): string[] {
  const labels: string[] = [];
  edges.forEach((e) => {
    if (e.source === id) e.possible_connections.forEach((c) => labels.push(`${id} –${c}→ ${e.target}`));
    if (e.target === id) e.possible_connections.forEach((c) => labels.push(`${e.source} –${c}→ ${id}`));
  });
  return labels;
}

function short(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function ChipColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="chipcol">
      <h4 className="panel-title">{title}</h4>
      <div className="chips">
        {items.length === 0 && <span className="muted">—</span>}
        {items.map((it) => (
          <span className="chip static" key={it}>
            {it}
          </span>
        ))}
      </div>
    </div>
  );
}

function DatasetsCard({ datasets }: { datasets: BrowserDataset[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="card">
      <h2>Datasets</h2>
      {datasets.length === 0 && <div className="muted">No datasets loaded.</div>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Version</th>
              <th>Imported</th>
              <th>Nodes</th>
              <th>Edges</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <DatasetRow
                key={d.name}
                ds={d}
                open={open === d.name}
                onToggle={() => setOpen(open === d.name ? null : d.name)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DatasetRow({
  ds,
  open,
  onToggle,
}: {
  ds: BrowserDataset;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>{ds.name}</td>
        <td className="mono">{ds.version ?? "—"}</td>
        <td className="muted">{ds.imported_on ?? "—"}</td>
        <td>{ds.nodes.length}</td>
        <td>{ds.edges.length}</td>
        <td className="mono muted">{open ? "▾" : "▸"}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6}>
            <div className="row" style={{ marginTop: 4, gap: 22 }}>
              <ChipColumn title="Node types" items={ds.nodes} />
              <ChipColumn title="Edge types" items={ds.edges} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function VersionsPanel({
  title,
  versions,
  morkVersions,
}: {
  title: string;
  versions?: VersionEntry[];
  morkVersions?: string[];
}) {
  return (
    <div>
      <h3 className="panel-title">{title}</h3>
      {morkVersions ? (
        <div className="chips">
          {morkVersions.map((v) => (
            <span className="chip static" key={v}>
              {v}
            </span>
          ))}
          {!morkVersions.length && <span className="muted">No versions.</span>}
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Created</th>
              <th>Changed datasets</th>
            </tr>
          </thead>
          <tbody>
            {(versions ?? []).map((v) => (
              <tr key={v.version}>
                <td className="mono">{v.version}</td>
                <td className="muted">
                  {v.created_at ? new Date(v.created_at).toLocaleString() : "—"}
                </td>
                <td>{v.num_changed ?? v.changed_datasets?.length ?? "—"}</td>
              </tr>
            ))}
            {!versions?.length && (
              <tr>
                <td colSpan={3} className="muted">
                  No versions.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
