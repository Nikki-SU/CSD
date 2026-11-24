import { useState } from 'react'
import { api } from '../api'
import { useJobData, type Figure } from '../useJob'

type Row = { fig: Figure; smiles: string; source: string }

export default function ReportPage() {
  const { job, figures, labels, loading } = useJobData()
  const [copied, setCopied] = useState<number | null>(null)
  const copy = (i: number, text: string) => {
    if (navigator.clipboard) void navigator.clipboard.writeText(text)
    setCopied(i)
    window.setTimeout(() => setCopied(null), 1200)
  }

  // 报告只列识别正确的真古董对应条目：人标 correct 或画对(redraw/gap 里有 SMILES 的)
  const confirmed = new Set(labels.filter((r) => ['correct', 'style_ok'].includes(r.verdict)).map((r) => r.figure_id))
  const rows: Row[] = labels
    .filter((r) => confirmed.has(r.figure_id) || (r.redrawn_smiles && ['redraw', 'gap'].includes(r.verdict)))
    .map((r) => {
      const fig = figures.find((f) => f.figure_id === r.figure_id)
      return {
        fig: fig || { figure_id: r.figure_id, image: '', article: '未知', page: 0, conf: 0 },
        smiles: r.redrawn_smiles || '（识别正确，SMILES 见导出）',
        source: fig ? `${fig.article} · 第${fig.page}页` : r.figure_id,
      }
    })

  if (loading) return <div className="page on"><h1 className="title">报告</h1><div className="card">加载中…</div></div>

  return (
    <div className="page on">
      <h1 className="title">报告</h1>
      <div className="card">
        {rows.length === 0 ? (
          <div style={{ color: 'var(--muted)' }}>暂无已确认结果。去「审阅」判定正确的结构式后，这里会列出报告。</div>
        ) : (
          <table>
            <thead><tr><th>原图</th><th>来源</th><th>SMILES</th><th>可追溯</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.fig.figure_id}>
                  <td>{job && r.fig.image ? <img src={api.fileUrl(job.job_id, r.fig.image)} alt={r.fig.figure_id} style={{ maxWidth: 90, maxHeight: 50, objectFit: 'contain' }} /> : r.fig.figure_id}</td>
                  <td>{r.source}</td>
                  <td>{r.smiles}<button className="btn copy" onClick={() => copy(i, r.smiles)}>{copied === i ? '已复制' : '复制'}</button></td>
                  <td>{r.fig.article}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div style={{ marginTop: 16 }}>
          {job && <a className="btn pri" href={api.exportUrl(job.job_id)}>导出 ZIP</a>}
        </div>
        <div className="devpanel">
          <b>输出这一段的中间产物</b>
          <div className="steps">
            <div className="step"><b>输入</b><span>人工判定（真值）</span></div>
            <div className="step"><b>中间产物</b><span>重画→SMILES</span></div>
            <div className="step"><b>输出</b><span>SMILES 清单 + 可追溯来源</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
