import { useEffect, useState } from 'react'
import { api } from '../api'
import { useJobData } from '../useJob'

type Overview = { jobs: number; figures: number; reviewed: number; rejected: number; by_status: Record<string, number> }

export default function DiagPage() {
  const { job, figures, labels, loading } = useJobData()
  const [ov, setOv] = useState<Overview | null>(null)
  const [tab, setTab] = useState<'topo' | 'match'>('topo')

  useEffect(() => { api.overview().then(setOv).catch(() => setOv(null)) }, [])

  const correct = labels.filter((r) => r.verdict === 'correct').length
  const wrong = labels.filter((r) => ['wrong', 'none', 'redraw'].includes(r.verdict)).length
  // 命中率分母为已审图数（真实数据），没有就显示 —
  const hit = (n: number) => labels.length ? `${(n / labels.length * 100).toFixed(0)}%` : '—'

  if (loading) return <div className="page on"><h1 className="title">归因对比</h1><div className="card">加载中…</div></div>

  return (
    <div className="page on">
      <h1 className="title">归因对比</h1>
      <div className="card">
        <div style={{ color: 'var(--muted)', marginBottom: 10 }}>真实统计（任务 {ov?.jobs ?? 0} · 结构式 {ov?.figures ?? 0} · 已审 {labels.length}）</div>
        <table>
          <thead><tr><th>模式</th><th title="分母为已审图数">正确判定率</th><th>错判/重画</th><th>已审数</th></tr></thead>
          <tbody>
            <tr><td>人工审阅</td><td>{hit(correct)}</td><td>{wrong}</td><td>{labels.length}</td></tr>
            <tr><td>MolDet 检出</td><td>{figures.length ? `${figures.length} 张候选` : '—'}</td><td>—</td><td>—</td></tr>
          </tbody>
        </table>
      </div>
      <div className="seg">
        <button className={tab === 'topo' ? 'on' : ''} onClick={() => setTab('topo')}>拓扑不准</button>
        <button className={tab === 'match' ? 'on' : ''} onClick={() => setTab('match')}>图匹配不准</button>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        {tab === 'topo' ? (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>被标错的图（回流拓扑训练的负样本）</div>
            {labels.filter((r) => ['wrong', 'redraw'].includes(r.verdict)).length === 0 ? (
              <div style={{ color: 'var(--muted)' }}>暂无错判标注。去「审阅」或「拓扑标注」标几张就有数据。</div>
            ) : labels.filter((r) => ['wrong', 'redraw'].includes(r.verdict)).map((r) => (
              <div className="row" key={r.figure_id} style={{ gap: 12, marginBottom: 10 }}>
                {job && <img src={api.fileUrl(job.job_id, figures.find((f) => f.figure_id === r.figure_id)?.image || '')} alt={r.figure_id} style={{ width: 100, objectFit: 'contain' }} />}
                <div className="step" style={{ background: 'var(--red-bg)', color: 'var(--red)' }}>{r.verdict}</div>
                <div style={{ color: 'var(--muted)', fontSize: 12 }}>{r.figure_id} · {r.reviewed_at}</div>
              </div>
            ))}
          </>
        ) : (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>图匹配候选分布</div>
            <div style={{ color: 'var(--muted)' }}>
              {labels.length ? labels.map((r) => `${r.figure_id}:${r.selected_rank || '未选'}`).join(' · ') : '暂无标注数据。'}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
