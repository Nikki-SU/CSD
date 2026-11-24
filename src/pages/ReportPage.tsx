import { useState } from 'react'

const ROWS = [
  { id: 'Bayreuther1973_fig3', year: '1973', smiles: 'CC(=O)Nc1ccccc1', doi: '10.1002/…' },
  { id: 'Adams1918_fig1', year: '1918', smiles: 'OC(=O)c1ccccc1', doi: '待复核' },
]

export default function ReportPage() {
  const [copied, setCopied] = useState<number | null>(null)
  const copy = (i: number, text: string) => {
    if (navigator.clipboard) void navigator.clipboard.writeText(text)
    setCopied(i)
    window.setTimeout(() => setCopied(null), 1200)
  }
  return (
    <div className="page on">
      <h1 className="title">报告</h1>
      <div className="card">
        <table>
          <thead><tr><th>原图</th><th>年份</th><th>假古董 SMILES</th><th>可追溯</th></tr></thead>
          <tbody>
            {ROWS.map((r, i) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.year}</td>
                <td>{r.smiles}<button className="btn copy" onClick={() => copy(i, r.smiles)}>{copied === i ? '已复制' : '复制'}</button></td>
                <td>{r.doi}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ marginTop: 16 }}><button className="btn pri">导出</button></div>
        <div className="devpanel">
          <b>输出这一段的中间产物</b>
          <div className="steps">
            <div className="step"><b>输入</b><span>人工判定</span></div>
            <div className="step"><b>中间产物</b><span>重画→邻接矩阵</span></div>
            <div className="step"><b>输出</b><span>SMILES 清单</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
