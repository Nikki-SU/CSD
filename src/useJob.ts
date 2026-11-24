// 共享：找到最新一个"有结构式图"的任务，供审阅/风格/拓扑/报告/归因页读真数据。
import { useEffect, useState } from 'react'
import { api, type JobItem } from './api'

export type Figure = {
  figure_id: string
  image: string
  article: string
  page: number
  conf: number
  has_structure?: boolean | null
}

export type LabelRow = {
  figure_id: string
  verdict: string
  selected_rank: string
  redrawn_smiles: string
  reviewed_at: string
}

export function useJobData() {
  const [job, setJob] = useState<JobItem | null>(null)
  const [figures, setFigures] = useState<Figure[]>([])
  const [labels, setLabels] = useState<LabelRow[]>([])
  const [loading, setLoading] = useState(true)

  const reload = async () => {
    setLoading(true)
    try {
      const { jobs } = await api.jobs()
      // 找最新的、已产出结构式图的任务
      for (const j of [...jobs].reverse()) {
        try {
          const f = await api.figures(j.job_id)
          if (f?.figures?.length) {
            setJob(j)
            setFigures(f.figures)
            try { setLabels((await api.labels(j.job_id)).rows) } catch { setLabels([]) }
            setLoading(false)
            return
          }
        } catch { /* 该任务没有 figures，找下一个 */ }
      }
      setJob(null); setFigures([]); setLabels([])
    } catch { setJob(null) }
    setLoading(false)
  }

  useEffect(() => { void reload() }, [])
  return { job, figures, labels, loading, reload, setLabels }
}
