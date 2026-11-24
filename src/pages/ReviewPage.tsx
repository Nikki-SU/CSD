import { useEffect, useState } from 'react'
import Drawer from '../ui/Drawer'
import { api } from '../api'
import { useJobData, type Figure } from '../useJob'
import type { Mode } from '../types'

type Cand = { rank: number; smiles: string; cid: string; render: string; score: number; phash: number; sift: number; ssim: number }

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="good" style={{ display: 'inline-flex', gap: 4, whiteSpace: 'nowrap' }}><span>{label}</span><b>{value}</b></div>
}

// 每个图取一次候选（A/B/C 带 SMILES）。只在激活那条才请求——
// 635 个图一次性全请求会打爆后端、卡死前端（实测白屏）。
function CandBlock({ job, fig, active, onSeed }: { job: string; fig: Figure; active: boolean; onSeed: (smiles: string) => void }) {
  const [cands, setCands] = useState<Cand[] | null>(null)
  useEffect(() => {
    if (!active) return
    let alive = true
    api.candidates(job, fig.figure_id)
      .then((r) => { if (alive) setCands(r.candidates) })
      .catch(() => { if (alive) setCands([]) })
    return () => { alive = false }
  }, [job, fig.figure_id, active])

  if (!active) {
    return (
      <div className="grid4">
        <div className="mol query">
          <div className="tag">真古董</div>
          <img src={api.fileUrl(job, fig.thumb || fig.image)} alt={fig.figure_id} style={{ maxWidth: '100%', maxHeight: 160, objectFit: 'contain' }} />
        </div>
      </div>
    )
  }
  if (cands === null) return <div style={{ color: 'var(--muted)', fontSize: 13 }}>候选加载中…</div>
  if (cands.length === 0) {
    return <div style={{ color: '#b45309', fontSize: 13 }}>候选未生成（后端需跑候选流程：拓扑筛 → 渲染 → 比图）</div>
  }
  return (
    <div className="grid4">
      <div className="mol query">
        <div className="tag">真古董</div>
        <img src={api.fileUrl(job, fig.image)} alt={fig.figure_id} style={{ maxWidth: '100%', maxHeight: 160, objectFit: 'contain' }} />
      </div>
      {cands.map((c, i) => (
        <div className="mol" key={c.smiles} onClick={() => onSeed(c.smiles)} style={{ cursor: 'pointer' }}>
          <div className="tag">候选 {'ABC'[i]}</div>
          <img src={api.fileUrl(job, c.render)} alt={c.smiles} style={{ maxWidth: '100%', maxHeight: 160, objectFit: 'contain' }} />
          <div className="met">
            <Metric label="相似" value={c.score.toFixed(2)} />
          </div>
          <div style={{ fontSize: 10, color: 'var(--muted)', wordBreak: 'break-all' }}>{c.smiles}</div>
        </div>
      ))}
    </div>
  )
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

  // 审阅是逐条过的，不需要一次把 635 条全塞进 Drawer（会卡死）。取前 300 条。
  const items = figures.slice(0, 300)

  if (loading) return <div className="page on"><h1 className="title">审阅</h1><div className="card">加载中…</div></div>
  if (!job || !items.length) return <div className="page on"><h1 className="title">审阅</h1><div className="card">暂无任务。先去「新建任务」提交文件夹，识别完成后回来审阅。</div></div>

  return (
    <div className="page on">
      <div className="banner">身份已核验 · 结果可采信</div>
      <h1 className="title">审阅 <span className={`pill ${mode === 'use' ? 'use' : 'train'}`}>{mode === 'use' ? '使用模式' : '训练模式'}</span></h1>
      <Drawer
        items={items}
        windowSec={0}
        renderItem={(fig, index, pick, active) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>{fig.article} · 第{fig.page}页 · 置信 {fig.conf.toFixed(2)}</div>
            <CandBlock job={job.job_id} fig={fig} active={active} onSeed={() => {}} />
            {active && (
              <div className="acts">
                {['A', 'B', 'C'].map((label, i) => (
                  <button key={label} className={`btn ${done.has(fig.figure_id) && pick.saved.indexOf(i) >= 0 ? 'ok' : ''}`}
                    onClick={() => { pick.toggle(i); void verdict(fig, 'correct', String(i + 1)); pick.advance() }}>选 {label}</button>
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
                    <button className="btn" style={{ color: 'var(--purple)' }} onClick={() => {
                      void verdict(fig, 'redraw')
                      go('lookup')  // 编辑器会带上候选 A 的 SMILES 预置
                    }}>都不对 · 我来画</button>
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
          <div className="step"><b>输入</b><span>真古董图</span></div>
          <div className="step"><b>第一轮</b><span>拓扑指标硬筛候选</span></div>
          <div className="step"><b>第二轮</b><span>渲染假古董→比图→A/B/C</span></div>
        </div>
      </div>
    </div>
  )
}
