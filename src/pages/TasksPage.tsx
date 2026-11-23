import { useEffect, useState } from 'react'
import type { PageId } from '../App'
import { api, type JobItem } from '../api'

const STAGE_LABEL: Record<string, string> = {
  queued: '排队',
  ingest: '读取',
  docverify: '核验',
  render: '渲染',
  coarse: '粗判',
  fine: '精判',
  chemcheck: '化学校验',
  done: '完成',
  failed: '失败',
}

export default function TasksPage({ go }: { go: (id: PageId) => void }) {
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.jobs()
        setJobs(data.jobs)
        setError('')
      } catch (err) {
        setError((err as Error).message)
      }
    }
    void load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  if (error) {
    return (
      <>
        <h2>任务</h2>
        <div className="card danger">{error}</div>
      </>
    )
  }

  return (
    <>
      <h2>任务</h2>
      {jobs.length === 0 && (
        <div className="card">
          <p className="sub" style={{ margin: 0 }}>还没有任务。</p>
          <button className="act" style={{ marginTop: 10 }} onClick={() => go('new')}>去新建</button>
        </div>
      )}
      {jobs.map((job) => {
        const stage = job.progress?.stage || job.status
        const pct = job.progress?.pct ?? 0
        return (
          <div className="card between" key={job.job_id}>
            <div>
              <div className="mono" style={{ fontSize: 13 }}>{job.job_id}</div>
              <p className="lab" style={{ margin: '4px 0 0' }}>
                {job.created_at.slice(0, 16).replace('T', ' ')} · {job.source_type === 'pdf' ? 'PDF' : '图片'}
                {job.year ? ` · ${job.year}` : ''} · {job.source_ref.split(/[\\/]/).pop()}
              </p>
              {job.progress?.message && (
                <p className="lab" style={{ margin: '4px 0 0' }}>{job.progress.message}</p>
              )}
            </div>
            <div className="row">
              <span className="info" style={{ fontSize: 12 }}>
                {STAGE_LABEL[stage] || stage}{stage !== 'done' && stage !== 'failed' ? ` ${pct}%` : ''}
              </span>
              {(job.status === 'done' || job.status === 'partial') && (
                <button className="act" onClick={() => go('review')}>审阅</button>
              )}
            </div>
          </div>
        )
      })}
    </>
  )
}
