export type Asset = {
  name: string;
  type: string;
  link: string;
  source?: string;
  license?: string;
};

export type FootageCandidate = {
  key: string;
  title: string;
  creator: string;
  source: string;
  source_url: string;
  license_name: string;
  resolution: string;
  duration: number;
  style: string;
  auto_eligible: boolean;
  preliminary_score: number;
  [key: string]: unknown;
};

export type GenerationJob = {
  id: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled";
  progress: number;
  stage: string;
  current_short: number;
  quantity: number;
  elapsed_seconds?: number;
  error?: string | null;
  outputs: Array<{
    id?: string;
    title: string;
    video_url: string;
    download_url?: string;
    manifest_url?: string | null;
    manifest_download_url?: string | null;
    quality: { score?: number; approved?: boolean };
    video_quality: { approved?: boolean };
    sources: number;
  }>;
};

export type Production = {
  id: string;
  title: string;
  description: string;
  content_type: string;
  created_at: string;
  size_bytes: number;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  quality_score?: number | null;
  approved?: boolean | null;
  sources: number;
  video_url: string;
  download_url: string;
  manifest_url?: string | null;
  manifest_download_url?: string | null;
};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: options?.body instanceof FormData
      ? options.headers
      : { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `Request failed (${response.status})`);
  }
  return response.json();
}
