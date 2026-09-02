import type {
  AdaptersResponse,
  BrowserOverview,
  BuildJob,
  BuildRequest,
  ConfigFileContent,
  ConfigFileInfo,
  ConfigSaveResult,
  ConfigValidation,
  FlagInfo,
  QueryBackend,
  QueryResult,
  SpeciesEntry,
  ValidationResult,
} from "../types";

const BASE = "/api/console";

async function json<T>(p: Promise<Response>): Promise<T> {
  const res = await p;
  if (!res.ok) {
    const text = await res.text();
    let detail: unknown;
    try {
      detail = text ? JSON.parse(text)?.detail : undefined;
    } catch {
      detail = text;
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
}

export const api = {
  listSpecies: () =>
    json<{ species: SpeciesEntry[] }>(fetch(`${BASE}/species`)).then(
      (d) => d.species,
    ),

  listAdapters: (species: string, dataset: string) =>
    json<AdaptersResponse>(
      fetch(`${BASE}/species/${species}/datasets/${dataset}/adapters`),
    ),

  listWriters: () =>
    json<{ writers: string[] }>(fetch(`${BASE}/writers`)).then((d) => d.writers),

  listFlags: () =>
    json<{ flags: FlagInfo[] }>(fetch(`${BASE}/flags`)).then((d) => d.flags),

  validate: (req: BuildRequest) =>
    json<ValidationResult>(
      fetch(`${BASE}/builds/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }),
    ),

  createBuild: (req: BuildRequest) =>
    json<{ id: string; status: string; job: BuildJob }>(
      fetch(`${BASE}/builds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }),
    ),

  listBuilds: () =>
    json<{ builds: BuildJob[] }>(fetch(`${BASE}/builds`)).then((d) => d.builds),

  getBuild: (id: string) => json<BuildJob>(fetch(`${BASE}/builds/${id}`)),

  getLogs: (id: string, tail = 500) =>
    json<{ id: string; status: string; return_code: number | null; lines: string[] }>(
      fetch(`${BASE}/builds/${id}/logs?tail=${tail}`),
    ),

  cancelBuild: (id: string) =>
    json<{ id: string; action: string }>(
      fetch(`${BASE}/builds/${id}`, { method: "DELETE" }),
    ),

  resumeBuild: (id: string) =>
    json<{ id: string; status: string; resumed_from: string }>(
      fetch(`${BASE}/builds/${id}/resume`, { method: "POST" }),
    ),

  loadBuild: (id: string, target: "neo4j" | "mork") =>
    json<{ id: string; status: string; kind: string }>(
      fetch(`${BASE}/builds/${id}/load/${target}`, { method: "POST" }),
    ),

  retryLoad: (id: string) =>
    json<{ id: string; status: string; kind: string }>(
      fetch(`${BASE}/builds/${id}/retry`, { method: "POST" }),
    ),

  listOutput: (id: string) =>
    json<{
      output_dir: string;
      exists: boolean;
      count: number;
      truncated?: boolean;
      files: { path: string; size: number }[];
    }>(fetch(`${BASE}/builds/${id}/output`)),

  getGraphInfo: (id: string) =>
    json<{ present: boolean; summary?: GraphInfoSummary }>(
      fetch(`${BASE}/builds/${id}/graph-info`),
    ),

  outputDownloadUrl: (id: string, path: string) =>
    `${BASE}/builds/${id}/output/download?path=${encodeURIComponent(path)}`,

  // ===== Milestone 1: read-only query =====
  listQueryBackends: () =>
    json<{ backends: QueryBackend[] }>(fetch(`${BASE}/query/backends`)).then(
      (d) => d.backends,
    ),

  runQuery: (backend: string, query: string, limit = 200, timeoutMs = 10000) =>
    json<QueryResult>(
      fetch(`${BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backend, query, limit, timeout_ms: timeoutMs }),
      }),
    ),

  // ===== Milestone 2: browser =====
  browserOverview: () =>
    json<BrowserOverview>(fetch(`${BASE}/browser/overview`)),

  // ===== Milestone 3: config editing =====
  listConfigFiles: () =>
    json<{ files: ConfigFileInfo[] }>(fetch(`${BASE}/config/files`)).then(
      (d) => d.files,
    ),

  getConfigFile: (path: string) =>
    json<ConfigFileContent>(
      fetch(`${BASE}/config/file?path=${encodeURIComponent(path)}`),
    ),

  validateConfigFile: (path: string, content: string) =>
    json<ConfigValidation>(
      fetch(`${BASE}/config/file/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, content }),
      }),
    ),

  saveConfigFile: (path: string, content: string) =>
    json<ConfigSaveResult>(
      fetch(`${BASE}/config/file/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, content }),
      }),
    ),
};

export interface GraphInfoSummary {
  node_count: number | null;
  edge_count: number | null;
  dataset_count: number | null;
  last_updated_at: string | null;
  kg_format: string | null;
  data_size: string | null;
  top_entities: { name: string; count: number }[] | null;
  top_connections: { name: string; count: number }[] | null;
}
