import { useState } from 'react'
import type { Mode } from '../types'
import { MOCK_REPORT, MOCK_EXPORT } from '../mock'

export default function ReportPage({ mode }: { mode: Mode }) {
  const [tab, setTab] = useState<'final' | 'train'>('final')
  return (
    <>
      <h2>任务报告</h2>
      <div style={{ marginBottom: 12 }}>
        <span className={`pill ${tab === 'final' ? 'on' : ''}`} onClick={() => setTab('final')}>假古董与 SMILES</span>
        {mode === 'train' && (
          <span className={`pill ${tab === 'train' ? 'on' : ''}`} onClick={() => setTab('train')}>训练回流数据</span>
        )}
      </div>

      {tab === 'final' ? (
        <>
          <p className="sub">可入库的结构式</p>
          <div className="grid4" style={{ marginBottom: 14 }}>
            {MOCK_REPORT.map((r) => (
              <div key={r.year} className="card" style={{ margin: 0, background: 'var(--panel)' }}>
                <p className="lab" style={{ margin: 0 }}>{r.year}</p>
                <div style={{ fontSize: 22, fontWeight: 600 }}>{r.count}</div>
              </div>
            ))}
          </div>
          {MOCK_EXPORT.map((e) => (
            <div key={e.figure_id} className="card between">
              <span className="mono">{e.figure_id}</span>
              <span className="info">{e.source} · {e.result}</span>
            </div>
          ))}
          <button className="act">导出 CSV</button>
        </>
      ) : (
        <>
          <p className="sub">拓扑准确度 · 双模式对比</p>
          <div className="grid2">
            {['模式 A · 二值', '模式 B · 精确'].map((m) => (
              <div key={m} className="card">
                <div style={{ fontWeight: 600 }}>{m}</div>
                <p className="lab" style={{ marginTop: 8 }}>拓扑准确度 —</p>
                <p className="lab">hit@1 —</p>
                <p className="lab" style={{ margin: 0 }}>hit@3 —</p>
              </div>
            ))}
          </div>
          <button className="act">重跑对比</button>
        </>
      )}
    </>
  )
}
