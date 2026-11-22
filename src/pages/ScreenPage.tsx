import { useState } from 'react'
import { MOCK_TILES } from '../mock'

function ShapeSvg({ index }: { index: number }) {
  const stroke = '#5F5E5A'
  const common = { fill: 'none', stroke, strokeWidth: 1.2 }
  switch (index % 6) {
    case 0:
      return <svg viewBox="0 0 60 40"><polygon points="30,3 50,14 50,29 30,39 10,29 10,14" {...common} /><line x1="50" y1="14" x2="58" y2="10" {...common} /></svg>
    case 1:
      return <svg viewBox="0 0 60 40"><path d="M4 30 L12 16 L20 30 L28 8 L36 30 L44 18 L52 30" {...common} /></svg>
    case 2:
      return <svg viewBox="0 0 60 40"><rect x="12" y="8" width="36" height="24" {...common} /><line x1="12" y1="20" x2="48" y2="20" {...common} /></svg>
    case 3:
      return <svg viewBox="0 0 60 40"><polygon points="30,3 52,16 52,28 30,39 8,28 8,16" {...common} /><circle cx="30" cy="21" r="5" {...common} /></svg>
    case 4:
      return <svg viewBox="0 0 60 40"><path d="M6 28 Q20 4 34 28 T58 28" {...common} /></svg>
    default:
      return <svg viewBox="0 0 60 40"><polygon points="30,3 50,16 50,28 30,39 10,28 10,16" {...common} /><text x="30" y="24" textAnchor="middle" fontSize="11" fill={stroke}>Me</text></svg>
  }
}

export default function ScreenPage() {
  const [out, setOut] = useState<Set<number>>(new Set())
  const toggle = (i: number) => {
    setOut((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }
  const kept = MOCK_TILES.length - out.size

  return (
    <>
      <h2>结构式筛选</h2>
      <p className="sub"><span className="ok">图注初筛 ✓</span> → 图块筛选（训练模式专属）</p>
      <div className="row" style={{ fontSize: 12, marginBottom: 12 }}>
        <span>保留 <b>{kept}</b></span>
        <span className="danger">剔除 <b>{out.size}</b></span>
        <span className="push lab" style={{ margin: 0 }}>点图剔除，再点恢复</span>
      </div>
      <div className="grid5">
        {MOCK_TILES.map((t, i) => (
          <div key={t.figure_id} className={`tile ${out.has(i) ? 'out' : ''}`} onClick={() => toggle(i)}>
            <ShapeSvg index={i} />
            <p className="lab" style={{ margin: '4px 0 0' }}>{t.year} · p{t.page}</p>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 14 }}>
        <button className="act" onClick={() => setOut(new Set())}>撤销</button>{' '}
        <button className="act">取代基规则</button>{' '}
        <button className="act">保存本轮</button>
      </div>
    </>
  )
}
