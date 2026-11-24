import { useEffect, useRef, useState } from 'react'
import MolSvg from '../ui/MolSvg'

const SHAPES: Array<0 | 1 | 2 | 3> = [0, 1, 2, 3]

export default function ScreenPage() {
  const [group, setGroup] = useState(1)
  const [tiles, setTiles] = useState<number[]>(Array.from({ length: 100 }, (_, i) => i))
  const [keep, setKeep] = useState(100)
  const [cut, setCut] = useState(0)
  const [showNext, setShowNext] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)

  const loadGroup = () => {
    setTiles(Array.from({ length: 100 }, (_, i) => i))
    setKeep(100)
    setCut(0)
    setShowNext(false)
    if (scroller.current) scroller.current.scrollTop = 0
  }
  const checkBottom = () => {
    const s = scroller.current
    if (s && s.scrollTop + s.clientHeight >= s.scrollHeight - 120) setShowNext(true)
  }
  useEffect(() => {
    loadGroup()
  }, [group])
  const remove = (n: number) => {
    setTiles((t) => t.filter((x) => x !== n))
    setKeep((k) => k - 1)
    setCut((c) => c + 1)
  }

  return (
    <div className="page on">
      <h1 className="title">结构式筛选</h1>
      <div className="card screen-card">
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 14 }}>
          <div>第 {group} 组</div>
          <div style={{ marginLeft: 'auto', color: 'var(--muted)' }}>保留 <b>{keep}</b> · 剔除 <b>{cut}</b></div>
        </div>
        <div className="wf-scroll" ref={scroller} onScroll={checkBottom} onWheel={checkBottom} onTouchMove={checkBottom}>
          <div className="wf">
            {tiles.map((n) => (
              <div key={n} className="tile" onClick={() => remove(n)}>
                <MolSvg color="#26241f" variant={SHAPES[(n + group) % 4]} />
              </div>
            ))}
          </div>
        </div>
        {showNext && <div className="nextgroup" style={{ display: 'block' }}><button className="btn pri" onClick={() => setGroup((g) => g + 1)}>下一组 →</button></div>}
        <div className="devpanel">
          <b>瀑布流这一步</b>
          <div className="steps">
            <div className="step"><b>输入</b><span>图注初筛后的图块</span></div>
            <div className="step"><b>中间产物</b><span>画风聚类</span></div>
            <div className="step"><b>输出</b><span>干净结构式图集</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
