// 字段严格沿用 API_CONTRACT.md v0.3.1 的 snake_case，不做映射层。

export type Mode = 'use' | 'train'

export interface Features {
  edges: number
  rings: number
  ring_sizes: number[]
  labels: string[]
}

export interface Score {
  phash: number
  ssim: number
  topo_match: boolean
}

export interface Candidate {
  rank: number
  candidate_id: string
  render_path: string
  score: Score
  features: Features
}

export interface Figure {
  figure_id: string
  page: number
  bbox: [number, number, number, number]
  crop_path: string
  compare_path: string
  legible: boolean
  has_structure: boolean
  query_features: Features
  candidates: Candidate[]
}

export interface JobMeta {
  job_id: string
  created_at: string
  source_type: 'pdf' | 'image'
  source_ref: string
  style_profile: string
  status: 'queued' | 'running' | 'done' | 'partial' | 'failed'
  progress: number
  figures?: number
}

export interface Verdict {
  job_id: string
  figure_id: string
  selected_rank: number | null
  verdict: 'match' | 'miss' | 'illegible'
  redrawn_smiles: string
  reviewer: string
  reviewed_at: string
}

// 拓扑校对：四项的通过/标红状态。点标红即改，下一条自动保存。
export interface TopoCheck {
  edges: boolean
  rings: boolean
  ring_sizes: boolean
  labels: boolean
}

export const STORAGE_KEYS = {
  baseUrl: 'csd.baseUrl',
  pat: 'csd.pat',
  owner: 'csd.owner',
  repo: 'csd.repo',
  branch: 'csd.branch',
  reviewer: 'csd.reviewer',
  mode: 'csd.mode',
} as const
