import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export type PickApi = {
  saved: number[]
  toggle: (k: number) => void
  advance: () => void
  left: number
}

type Props<T> = {
  items: T[]
  renderItem: (item: T, index: number, pick: PickApi, active: boolean) => ReactNode
  windowSec?: number
  onAdvance?: (index: number) => void
}

// 一屏三条抽屉：中间激活、上下淡化可点移到中间。
// 标记按条目索引存在 data 上（不在 DOM），移回时保留。
// 时间窗到自动轮转；手动「立即轮转」= 确认加速，不阻塞。
export default function Drawer<T>({ items, renderItem, windowSec = 0, onAdvance }: Props<T>) {
  const [idx, setIdx] = useState(0)
  const [marks, setMarks] = useState<Record<number, number[]>>({})
  const [left, setLeft] = useState(0)
  const timer = useRef<number | null>(null)

  const clear = () => {
    if (timer.current !== null) {
      window.clearInterval(timer.current)
      timer.current = null
    }
  }
  useEffect(() => () => clear(), [])

  const arm = () => {
    clear()
    if (!windowSec) return
    setLeft(windowSec)
    timer.current = window.setInterval(() => {
      setLeft((prev) => {
        if (prev <= 1) {
          clear()
          setIdx((i) => i + 1)
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }
  const advance = () => {
    clear()
    onAdvance?.(idx)
    setIdx((i) => i + 1)
  }
  const toggle = (i: number, k: number) => {
    const cur = marks[i] ?? []
    const wasMarked = cur.indexOf(k) >= 0
    setMarks((m) => {
      const c = m[i] ?? []
      return { ...m, [i]: c.indexOf(k) >= 0 ? c.filter((x) => x !== k) : [...c, k] }
    })
    if (wasMarked) { clear(); setLeft(0) } else arm()
  }

  if (idx >= items.length) return <div className="card">已审完</div>

  return (
    <div className="turn">
      {[-1, 0, 1].map((off) => {
        const i = idx + off
        if (i < 0 || i >= items.length) {
          return <div key={off} className="slot dim" style={{ opacity: 0, pointerEvents: 'none' }}><div className="card" /></div>
        }
        const active = off === 0
        const pick: PickApi = {
          saved: marks[i] ?? [],
          toggle: (k: number) => toggle(i, k),
          advance,
          left,
        }
        return (
          <div
            key={off}
            className={`slot ${active ? 'active' : 'dim'}`}
            onClick={active ? undefined : () => { clear(); setIdx(i) }}
          >
            <div className="card">
              {renderItem(items[i], i, pick, active)}
              {active && (
                <>
                  <div className="cd">{left > 0 ? `${left}s 后轮转` : ''}</div>
                  <div className="acts">
                    <button className="btn" onClick={advance}>立即轮转 ↓</button>
                  </div>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
