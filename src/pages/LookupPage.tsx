import { useState } from 'react'
import { api } from '../api'
import { useJobData } from '../useJob'
import MolEditor from '../ui/MolEditor'

// 我来画 · 查库。从「都不对」进来，编辑器**预置候选 A 的结构**——
// 不从零画（整分子画不过来），只改 A 里不对的部分。
// 改完取 SMILES → 查库确认 → 回流。
export default function LookupPage() {
  const { job, figures, labels } = useJobData()
  const [target, setTarget] = useState(0)
  const [seed, setSeed] = useState('')
  const [smiles, setSmiles] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [result, setResult] = useState<'found' | 'gap' | null>(null)
  const [saved, setSaved] = useState(false)

  const fig = figures[target]

  const loadSeed = async () => {
    if (!job || !fig) return
    try {
      const c = await api.candidates(job.job_id, fig.figure_id)
      const a = c.candidates.find((x) => x.rank === 0) || c.candidates[0]
      setSeed(a?.smiles || '')
    } catch { setSeed('') }
    setLoaded(true)
  }

  const lookup = () => {
    const q = smiles.trim().toLowerCase()
    if (!q) return
    const hit = labels.find((r) => (r.redrawn_smiles || '').toLowerCase() === q)
    setResult(hit ? 'found' : 'gap')
    setSaved(false)
  }

  const markGap = async () => {
    if (!job || !fig) return
    try {
      await api.saveLabels({ job_id: job.job_id, rows: [{
        figure_id: fig.figure_id, verdict: 'gap', redrawn_smiles: smiles.trim(),
      }] })
      setSaved(true)
    } catch { /* saved 状态体现 */ }
  }

  return (
    <div className="page on">
      <h1 className="title">我来画 · 查库</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>在候选 A 上修改</div>
        {!loaded && (
          <div className="row" style={{ gap: 8 }}>
            <button className="btn pri" onClick={() => void loadSeed()} disabled={!fig}>
              载入候选 A 的结构{fig ? `（第${fig.page}页 ${fig.article}）` : ''}
            </button>
            {figures.length > 1 && (
              <select value={target} onChange={(e) => setTarget(Number(e.target.value))}>
                {figures.map((f, i) => <option key={f.figure_id} value={i}>第{f.page}页 · {f.article}</option>)}
              </select>
            )}
          </div>
        )}
        {loaded && (
          <>
            {seed
              ? <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>已预置候选 A：<code>{seed}</code>　只在不对的地方改</div>
              : <div style={{ fontSize: 12, color: '#b45309', marginBottom: 6 }}>该图候选尚未生成，编辑器为空，需手动绘制</div>}
            <MolEditor initialSmiles={seed} height={260} onChange={setSmiles} />
          </>
        )}
      </div>
      {loaded && (
        <div className="card">
          <div className="field"><label>修改后的 SMILES</label><input value={smiles} onChange={(e) => setSmiles(e.target.value)} placeholder="点编辑器下方「取当前 SMILES」" /></div>
          <div className="field" style={{ marginTop: 10 }}><label>来源</label><input readOnly value={fig ? `${fig.article} · 第${fig.page}页` : '暂无'} /></div>
          <div style={{ marginTop: 12 }}><button className="btn pri" onClick={lookup}>查数据库</button></div>
        </div>
      )}
      {result === 'found' && (
        <div className="card" style={{ borderColor: 'var(--green)' }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--green)', marginBottom: 10 }}>查到了 · 已回流库</div>
          <p>SMILES：{smiles}</p>
          <p>回流：匹配训练 + 拓扑训练</p>
        </div>
      )}
      {result === 'gap' && (
        <div className="card" style={{ borderColor: 'var(--red)' }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--red)', marginBottom: 10 }}>没查到 · 标记缺口</div>
          <p>库中无此结构 · 未入库</p>
          <p>{fig?.article} · DOI 待补</p>
          <button className="btn pri" onClick={() => void markGap()} disabled={saved}>{saved ? '已标记缺口' : '标记缺口并回流'}</button>
        </div>
      )}
    </div>
  )
}
