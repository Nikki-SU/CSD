// 本地后端 API 封装。地址存 localStorage，默认 http://127.0.0.1:8765。
import { STORAGE_KEYS } from './types'

export function baseUrl(): string {
  return (localStorage.getItem(STORAGE_KEYS.baseUrl) || 'http://127.0.0.1:8765').replace(/\/$/, '')
}

export function setBaseUrl(url: string): void {
  localStorage.setItem(STORAGE_KEYS.baseUrl, url.trim().replace(/\/$/, ''))
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${baseUrl()}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    })
  } catch {
    throw new Error(`连不上本地服务 ${baseUrl()}，先启动 python -m backend.server`)
  }
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    const message = (data as { error?: string } | null)?.error || `HTTP ${res.status}`
    throw new Error(message)
  }
  return data as T
}

export interface JobItem {
  job_id: string
  created_at: string
  source_type: 'pdf' | 'image'
  source_ref: string
  style_profile: string
  year?: string
  status: string
  progress?: { stage: string; pct: number; message: string }
}

export async function probe(): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl()}/api/health`, { cache: 'no-store' })
    return res.ok
  } catch {
    return false
  }
}

export const api = {
  health: () => request<{ status: string; version: string; data_dir: string }>('/api/health'),
  jobs: () => request<{ count: number; jobs: JobItem[] }>('/api/jobs'),
  job: (id: string) => request<JobItem & { progress?: { stage: string; pct: number; message: string } }>(`/api/jobs/${id}`),
  result: (id: string) => request<Record<string, unknown>>(`/api/jobs/${id}/result`),
  doc: (id: string) => request<Record<string, unknown>>(`/api/jobs/${id}/doc`),
  settings: () => request<{ mineru_key_set: boolean; mineru_key_tail: string; mineru_model: string }>('/api/settings'),
  saveSettings: (payload: { mineru_key?: string; mineru_model?: string }) =>
    request<{ mineru_key_set: boolean; mineru_key_tail: string }>('/api/settings', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  scan: (path: string) =>
    request<{ path: string; count: number; items: { name: string; path: string; size: number; kind: string; year: number | null }[] }>(
      `/api/scan?path=${encodeURIComponent(path)}`,
    ),
  createBatch: (paths: string[], source_type: string) =>
    request<{ created: number; jobs: JobItem[]; errors: { path: string; error: string }[] }>('/api/jobs/batch', {
      method: 'POST',
      body: JSON.stringify({ paths, source_type }),
    }),
  saveLabels: (payload: unknown) =>
    request<{ count: number }>('/api/labels', { method: 'POST', body: JSON.stringify(payload) }),
  fileUrl: (jobId: string, rel: string) => `${baseUrl()}/files/${jobId}/${rel}`,
}
