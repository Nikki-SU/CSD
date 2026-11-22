// 全部为代码内合成的占位数据，不含任何真实文献内容（公库零数据红线）。
// 后端就绪后由 GitHub Contents API 读取私库结果替换，界面不造假数据。
import type { Features, Figure, JobMeta } from './types'

const feat = (edges: number, rings: number, ringSizes: number[], labels: string[]): Features => ({
  edges,
  rings,
  ring_sizes: ringSizes,
  labels,
})

export function scoreColor(value: number, ok: boolean): string {
  return ok && value >= 0.8 ? 'ok' : 'bad'
}

export const MOCK_JOBS: JobMeta[] = [
  {
    job_id: 'j_20261122_1030_a1b2c3',
    created_at: '2026-11-22T10:30:00Z',
    source_type: 'pdf',
    source_ref: 'inbox/j_20261122_1030_a1b2c3/source.pdf',
    style_profile: 'default_1970s',
    status: 'running',
    progress: 42,
    figures: 12,
  },
  {
    job_id: 'j_20261121_1547_c9d4e1',
    created_at: '2026-11-21T15:47:00Z',
    source_type: 'pdf',
    source_ref: 'inbox/j_20261121_1547_c9d4e1/source.pdf',
    style_profile: 'default_1960s',
    status: 'done',
    progress: 100,
    figures: 8,
  },
  {
    job_id: 'j_20261120_0912_f30a77',
    created_at: '2026-11-20T09:12:00Z',
    source_type: 'pdf',
    source_ref: 'inbox/j_20261120_0912_f30a77/source.pdf',
    style_profile: 'default_1950s',
    status: 'failed',
    progress: 0,
  },
]

export const MOCK_FIGURE: Figure = {
  figure_id: 'p004_f01',
  page: 4,
  bbox: [112, 240, 389, 331],
  crop_path: 'outbox/mock/crops/p004_f01.png',
  compare_path: 'outbox/mock/compare/p004_f01.png',
  legible: true,
  has_structure: true,
  query_features: feat(14, 1, [5], ['N', 'O']),
  candidates: [
    {
      rank: 1,
      candidate_id: 'c_7f3a91d2',
      render_path: 'outbox/mock/compare/p004_f01_r1.png',
      score: { phash: 0.91, ssim: 0.82, topo_match: true },
      features: feat(14, 1, [5], ['N', 'O']),
    },
    {
      rank: 2,
      candidate_id: 'c_3e8b01fa',
      render_path: 'outbox/mock/compare/p004_f01_r2.png',
      score: { phash: 0.78, ssim: 0.71, topo_match: true },
      features: feat(14, 1, [5], ['N']),
    },
    {
      rank: 3,
      candidate_id: 'c_a1c96e04',
      render_path: 'outbox/mock/compare/p004_f01_r3.png',
      score: { phash: 0.74, ssim: 0.66, topo_match: false },
      features: feat(15, 1, [6], ['N', 'O']),
    },
  ],
}

export const MOCK_TILES = Array.from({ length: 20 }, (_, i) => ({
  figure_id: `p${String((i % 8) + 1).padStart(3, '0')}_f${String((i % 5) + 1).padStart(2, '0')}`,
  year: 1952 + (i % 8),
  page: (i % 8) + 1,
}))

export const MOCK_REPORT = [
  { year: '1950s', count: 3 },
  { year: '1960s', count: 2 },
  { year: '1970s', count: 3 },
  { year: '1980s', count: 1 },
]

export const MOCK_EXPORT = [
  { figure_id: 'p004_f01', source: '1959 · JACS', result: '假古董 → SMILES' },
  { figure_id: 'p011_f03', source: '1964 · JCS', result: '假古董 → SMILES' },
  { figure_id: 'p018_f02', source: '1977 · Chem Commun', result: '假古董 → SMILES' },
]
