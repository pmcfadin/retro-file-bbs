/** Typed API client for the admin backend. */

const BASE = "/api";

export interface Category {
  area: string;
  count: number;
  description: string;
  display_name: string;
}

export interface FileEntry {
  path: string;
  area: string;
  filename: string;
  size: number;
  mtime: number;
  description: string;
}

export interface FilesResponse {
  files: FileEntry[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface SessionEntry {
  session_id: string;
  peer_ip: string;
  peer_port: number;
  connected_at: string;
  current_state: string;
}

export interface ConnectionEntry {
  session_id: string;
  peer_ip: string;
  peer_port: number;
  connected_at?: string;
  disconnected_at?: string;
  event: string;
}

export interface ServerConfig {
  version: string;
  telnet_port: number;
  web_port: number;
  cpm_root: string;
  db_path: string;
}

export interface IndexerStatusResponse {
  running: boolean;
  last_run: string | null;
  last_result: string | null;
  file_count: number;
  category_count: number;
}

export interface DskMetadata {
  format: string;
  display_name: string;
  system: string;
  file_count: number;
  image_size: number;
}

export interface DskPreview extends DskMetadata {
  file_list: string[];
}

export interface ExtractResponse {
  staging_id: string;
  files: { name: string; size: number }[];
  dsk_metadata: DskMetadata | null;
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  getConfig: () => fetchJSON<ServerConfig>(`${BASE}/config`),
  patchConfig: (data: Partial<Pick<ServerConfig, "version" | "telnet_port" | "web_port" | "cpm_root" | "db_path">>) =>
    fetchJSON<{ status: string; updated: Record<string, unknown> }>(`${BASE}/config`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  getCategories: () => fetchJSON<Category[]>(`${BASE}/categories`),

  getFiles: (params: { area?: string; search?: string; page?: number; per_page?: number }) => {
    const qs = new URLSearchParams();
    if (params.area) qs.set("area", params.area);
    if (params.search) qs.set("search", params.search);
    if (params.page) qs.set("page", String(params.page));
    if (params.per_page) qs.set("per_page", String(params.per_page));
    return fetchJSON<FilesResponse>(`${BASE}/files?${qs}`);
  },

  getFileDetail: (path: string) => fetchJSON<FileEntry>(`${BASE}/files/${path}`),

  getDskPreview: (path: string) => fetchJSON<DskPreview>(`${BASE}/preview/${path}`),

  patchFile: (path: string, data: { description?: string; area?: string }) =>
    fetchJSON<{ status: string }>(`${BASE}/files/${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteFile: (path: string) =>
    fetchJSON<{ status: string }>(`${BASE}/files/${path}`, { method: "DELETE" }),

  uploadFile: (file: File, area: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetchJSON<{ status: string; path: string; size: number }>(
      `${BASE}/upload?area=${encodeURIComponent(area)}`,
      { method: "POST", body: form }
    );
  },

  extractArchive: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetchJSON<ExtractResponse>(`${BASE}/extract`, { method: "POST", body: form });
  },

  commitExtract: (staging_id: string, area: string, files: string[]) =>
    fetchJSON<{ status: string; committed: string[] }>(`${BASE}/extract/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ staging_id, area, files }),
    }),

  getSessions: () => fetchJSON<SessionEntry[]>(`${BASE}/sessions`),
  getConnections: () => fetchJSON<ConnectionEntry[]>(`${BASE}/connections`),

  getIndexerStatus: () => fetchJSON<IndexerStatusResponse>(`${BASE}/indexer/status`),
  runIndexer: () => fetchJSON<{ status: string }>(`${BASE}/indexer/run`, { method: "POST" }),
};
