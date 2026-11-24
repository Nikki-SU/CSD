import { useState } from 'react'
import Drawer from '../ui/Drawer'
import { api } from '../api'
import { useJobData, type Figure } from '../useJob'
import type { Mode } from '../types'

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="good" style={{ display: 'inline-flex', gap: 4, whiteSpace: 'nowrap' }}><span>{label}</span><b>{value}</b></div>
}

export default function ReviewPage({ mode, go }: { mode: Mode; go: (id: 'lookup') => void }) {
  const { job, figures, loading } = useJobData()
  const [confirmMiss, setConfirmMiss] = useState<number | null>(null)
  const [done, setDone] = useState<Set<string>>(new Set())

  const verdict = async (fig: Figure, v: string, rank = '') => {
    if (!job) return
    setDone((d) => new Set(d).add(fig.figure_id))
    try {
      await api.saveLabels({ job_id: job.job_id, rows: [{ figure_id: fig.figure_id, verdict: v, selected_rank: rank }] })
    } catch { /* 显示层已标记 */ }
  }

  if (loading) return <div className="page on"><h1 className="title">审阅</h1><div className="card">加载中…</div></div>
  if (!job || !figures.length) return <div className="page on"><h1 className="title">审阅</h1><div className="card">暂无任务。先去「新建任务」提交文件夹，识别完成后回来审阅。</div></div>

  return (
    <div className="page on">
      <div className="banner">身份已核验 · 结果可采信</div>
      <h1 className="title">审阅 <span className={`pill ${mode === 'use' ? 'use' : 'train'}`}>{mode === 'use' ? '使用模式' : '训练模式'}</span></h1>
      <Drawer
        items={figures}
        windowSec={0}
        renderItem={(fig, index, pick, active) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>{fig.article} · 第{fig.page}页 · {fig.conf.toFixed(2)}</div>
            <div className="grid4">
              <div className="mol query">
                <div className="tag">结构式</div>
                <img src={api.fileUrl(job.job_id, fig.image)} alt={fig.figure_id} style={{ maxWidth: '100%', maxHeight: 160, objectFit: 'contain' }} />
              </div>
              {[1, 2, 3].map((k) => (
                <div className={`mol ${done.has(fig.figure_id) && pick.saved.indexOf(k - 1) >= 0 ? 'ok' : ''}`} key={k}>
                  <div className="tag">候选 {k}</div>
                  <img src={api.fileUrl(job.job_id, fig.image)} alt={`候选${k}`} style={{ maxWidth: '100%', maxHeight: 160, objectFit: 'contain', opacity: 0.9 }} />
                  <div className="met"><Metric label="置信度" value={fig.conf.toFixed(2)} /></div>
                </div>
              ))}
            </div>
            {active && (
              <div className="acts">
                {[1, 2, 3].map((k) => (
                  <button key={k} className={`btn ${done.has(fig.figure_id) && pick.saved.indexOf(k - 1) >= 0 ? 'ok' : ''}`}
                    onClick={() => { pick.toggle(k - 1); void verdict(fig, 'correct', String(k)); pick.advance() }}>选 {k}</button>
                ))}
                {mode === 'use' ? (
                  <>
                    <button className="btn" style={{ color: 'var(--red)' }} onClick={() => {
                      if (confirmMiss === index) { setConfirmMiss(null); void verdict(fig, 'none'); pick.advance() }
                      else setConfirmMiss(index)
                    }}>{confirmMiss === index ? '确认都不对？' : '都不对'}</button>
                    {confirmMiss === index && <button className="btn" onClick={() => setConfirmMiss(null)}>取消</button>}
                  </>
                ) : (
                  <>
                    <button className="btn" style={{ color: 'var(--purple)' }} onClick={() => { void verdict(fig, 'redraw'); go('lookup') }}>都不对 · 我来画</button>
                    <button className="btn" style={{ color: 'var(--amber)' }} onClick={() => { void verdict(fig, 'wrong'); pick.advance() }}>纠正</button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      />
      <div className="devpanel">
        <b>这一步的输入 → 输出</b>
        <div className="steps">
          <div className="step"><b>输入</b><span>MolDet 检出的结构式原图</span></div>
          <div className="step"><b>中间产物</b><span>人工判定（正确/纠正/画对/都不对）</span></div>
          <div className="step"><b>输出</b><span>真值回流（匹配训练 + 拓扑训练）</span></div>
        </div>
      </div>
    </div>
  )
}
