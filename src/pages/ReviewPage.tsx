import { useState } from 'react'
import type { PageId } from '../App'
import type { Features, TopoCheck } from '../types'
import { MOCK_FIGURE } from '../mock'

function MolSvg({ kind }: { kind: 'ring' | 'chain' | 'square' }) {
  const s = { fill: 'none', stroke: '#5F5E5A', strokeWidth: 1.2 }
  if (kind === 'square') return <svg viewBox="0 0 60 40"><rect x="14" y="9" width="32" height="22" {...s} /><line x1="46" y1="14" x2="56" y2="9" {...s} /></svg>
  if (kind === 'chain') return <svg viewBox="0 0 60 40"><path d="M8 30 L20 10 L32 30 L44 10 L56 30" {...s} /></svg>
  return <svg viewBox="0 0 60 40"><polygon points="30,3 50,14 50,29 30,39 10,29 10,14" {...s} /><line x1="50" y1="14" x2="58" y2="10" {...s} /></svg>
}

function metricCells(features: Features, reference: Features, checks?: TopoCheck) {
  const items = [
    { key: 'edges' as const, label: '边数', value: features.edges, ref: reference.edges },
    { key: 'rings' as const, label: '环数', value: features.rings, ref: reference.rings },
    { key: 'ring_sizes' as const, label: '环大小', value: features.ring_sizes.join('|'), ref: reference.ring_sizes.join('|') },
    { key: 'labels' as const, label: '标签', value: features.labels.join(' '), ref: reference.labels.join(' ') },
  ]
  return items.map((it, idx) => {
    const match = it.value === it.ref
    const marked = checks ? !checks[it.key] : !match
    return (
      <div key={it.key} className={`metric ${marked ? 'bad' : ''}`}>
        <p className="lab" style={{ margin: '0 0 3px' }}>{idx + 1} {it.label}</p>
        <b>{it.value}</b>
      </div>
    )
  })
}

export default function ReviewPage({ go }: { go: (id: PageId) => void }) {
  const [tab, setTab] = useState<'choose' | 'topo'>('choose')
  const [selected, setSelected] = useState<number | null>(null)
  const [checks, setChecks] = useState<TopoCheck>({ edges: true, rings: true, ring_sizes: true, labels: false })
  const figure = MOCK_FIGURE

  const toggleCheck = (key: keyof TopoCheck) => {
    setChecks((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <>
      <h2>审阅</h2>
      <div style={{ marginBottom: 14 }}>
        <span className={`pill ${tab === 'choose' ? 'on' : ''}`} onClick={() => setTab('choose')}>3 选一</span>
        <span className={`pill ${tab === 'topo' ? 'on' : ''}`} onClick={() => setTab('topo')}>拓扑校对</span>
      </div>

      {tab === 'choose' ? (
        <>
          <p className="lab">{figure.figure_id} · 34/96</p>
          <div className="grid4">
            <div className="cand">
              <p className="lab">原图</p>
              <MolSvg kind="ring" />
              <p className="lab" style={{ margin: '4px 0 0' }}>边14 环1 环5 N O</p>
            </div>
            {figure.candidates.map((c) => (
              <div key={c.candidate_id} className={`cand ${selected === c.rank ? 'sel' : ''}`}>
                <p className="lab">候选 {c.rank}</p>
                <MolSvg kind={c.rank === 3 ? 'square' : c.rank === 2 ? 'chain' : 'ring'} />
                <div className="grid4" style={{ gap: 4, marginTop: 6 }}>
                  {metricCells(c.features, figure.query_features)}
                </div>
                <button className="act" style={{ width: '100%', marginTop: 6 }} onClick={() => setSelected(c.rank)}>选 {c.rank}</button>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <button className="act" onClick={() => go('redraw')}>全错 → 重画</button>{' '}
            <button className="act">不可读</button>{' '}
            <button className="act">下一条 J</button>
          </div>
        </>
      ) : (
        <>
          <p className="sub">审所有原图识别到的拓扑，不对的标红</p>
          <div className="grid4">
            {(['edges', 'rings', 'ring_sizes', 'labels'] as const).map((key, i) => {
              const labels = { edges: '边数', rings: '环数', ring_sizes: '环大小', labels: '标签' }
              const vals = { edges: String(figure.query_features.edges), rings: String(figure.query_features.rings), ring_sizes: figure.query_features.ring_sizes.join('|'), labels: figure.query_features.labels.join(' ') }
              return (
                <div
                  key={key}
                  className={`metric ${!checks[key] ? 'bad' : ''}`}
                  style={{ cursor: 'pointer' }}
                  onClick={() => toggleCheck(key)}
                >
                  <p className="lab" style={{ margin: '0 0 3px' }}>{i + 1} {labels[key]}</p>
                  <b>{vals[key]}</b>
                </div>
              )
            })}
          </div>
          <p className="lab" style={{ margin: '12px 0 6px' }}>点指标标红即改 · 下一条自动保存</p>
          <button className="act">下一条 J →</button>
        </>
      )}
    </>
  )
}
