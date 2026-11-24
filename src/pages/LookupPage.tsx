import { useState } from 'react'
import { api } from '../api'
import { useJobData } from '../useJob'

// 我来画 · 查库。训练模式可用：画对的结构取 SMILES 查本地已回流库；
// 查不到则标记缺口（记 DOI/年份）——「查无」本身是发现信号。
// 化学编辑器是选型占位（JSME），SMILES 由人填；拓扑由后端 RDKit 解析，前端不算。
export default function LookupPage() {
  const { job, figures, labels } = useJobData()
  const [smiles, setSmiles] = useState('')
  const [result, setResult] = useState<'found' | 'gap' | null>(null)
  const [gapInfo, setGapInfo] = useState('')
  const [saved, setSaved] = useState(false)

  const lookup = () => {
    const q = smiles.trim().toLowerCase()
    if (!q) return
    // 查本地已回流结构（labels 里 redrawn_smiles / 审阅正确的条目）
    const hit = labels.find((r) => (r.redrawn_smiles || '').toLowerCase() === q)
    if (hit) { setResult('found'); setSaved(false) }
    else {
      setResult('gap')
      const art = figures[0]?.article || '未知文献'
      setGapInfo(`${art} · DOI 待补 · ${new Date().getFullYear()}`)
      setSaved(false)
    }
  }

  const markGap = async () => {
    if (!job) return
    const target = figures[0]
    if (!target) return
    try {
      await api.saveLabels({ job_id: job.job_id, rows: [{
        figure_id: target.figure_id, verdict: 'gap', redrawn_smiles: smiles.trim(),
      }] })
      setSaved(true)
    } catch { /* 显示失败由 saved 状态体现 */ }
  }

  return (
    <div className="page on">
      <h1 className="title">我来画 · 查库</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>画出正确结构</div>
        <div className="row">
          <div style={{ flex: 1, border: '1px dashed var(--line)', borderRadius: 8, height: 150, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)' }}>
            化学结构编辑器（JSME）占位 · 导出 SMILES
          </div>
          <div style={{ flex: 1 }}>
            <div className="field"><label>导出的 SMILES</label><input value={smiles} onChange={(e) => setSmiles(e.target.value)} placeholder="CC(=O)Nc1ccccc1" /></div>
            <div className="field" style={{ marginTop: 12 }}>
              <label>来源</label>
              <input readOnly value={job && figures[0] ? `${figures[0].article} · 第${figures[0].page}页` : '暂无任务'} />
            </div>
            <div style={{ marginTop: 14 }}><button className="btn pri" onClick={lookup}>查数据库</button></div>
          </div>
        </div>
      </div>
      {result === 'found' && (
        <div className="card" style={{ borderColor: 'var(--green)' }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--green)', marginBottom: 10 }}>查到了 · 已回流库</div>
          <p>SMILES：{smiles}</p>
          <p>回流：匹配训练 + 拓扑训练（真值已入本地库）</p>
        </div>
      )}
      {result === 'gap' && (
        <div className="row" style={{ marginTop: 14 }}>
          <div className="card" style={{ flex: 1, borderColor: 'var(--red)' }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--red)', marginBottom: 10 }}>没查到 · 标记缺口</div>
            <p>库中无此结构 · 未入库</p>
            <p>{gapInfo}</p>
            <button className="btn pri" onClick={() => void markGap()} disabled={saved}>{saved ? '已标记缺口' : '标记缺口并回流'}</button>
          </div>
        </div>
      )}
      {!result && <div style={{ color: 'var(--muted)', marginTop: 14 }}>填 SMILES 后点「查数据库」；查到的结构回流训练，查不到的记 DOI/年份作发现信号。</div>}
    </div>
  )
}
