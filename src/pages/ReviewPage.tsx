import { useState } from 'react'
import Drawer from '../ui/Drawer'
import MolSvg from '../ui/MolSvg'
import type { Mode } from '../types'

type Figure = { id: number }
const ITEMS: Figure[] = Array.from({ length: 10 }, (_, i) => ({ id: i }))

function Metric({ label, value, bad }: { label: string; value: string; bad?: boolean }) {
  return <div className={bad ? 'bad' : 'good'}><span>{label}</span><b>{value}</b></div>
}

export default function ReviewPage({ mode, go }: { mode: Mode; go: (id: 'lookup') => void }) {
  const [confirmMiss, setConfirmMiss] = useState<number | null>(null)

  return (
    <div className="page on">
      <div className="banner">身份已核验 · 结果可采信</div>
      <h1 className="title">审阅 <span className={`pill ${mode === 'use' ? 'use' : 'train'}`}>{mode === 'use' ? '使用模式' : '训练模式'}</span></h1>
      <Drawer
        items={ITEMS}
        windowSec={0}
        renderItem={(_item, index, pick, active) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>图 {index + 1}</div>
            <div className="grid4">
              <div className="mol query">
                <div className="tag">原图</div>
                <MolSvg color="#26241f" />
                <div className="met"><Metric label="环数" value="1" /><Metric label="环大小" value="6" /><Metric label="标签" value="N O" /></div>
              </div>
              {[1, 2, 3].map((k) => (
                <div className="mol" key={k}>
                  <div className="tag">候选 {k}</div>
                  <MolSvg color="#185fa5" />
                  <div className="met">
                    <Metric label="环数" value={k === 3 ? '2' : '1'} bad={k === 3} />
                    <Metric label="环大小" value={k === 3 ? '6,5' : '6'} bad={k === 3} />
                    <Metric label="标签" value={k === 2 ? 'N' : 'N O'} bad={k === 2} />
                  </div>
                </div>
              ))}
            </div>
            {active && (
              <div className="acts">
                {[1, 2, 3].map((k) => {
                  const chosen = pick.saved.indexOf(k - 1) >= 0
                  return (
                    <button key={k} className={`btn ${chosen ? 'ok' : ''}`} onClick={() => { pick.toggle(k - 1); pick.advance() }}>选 {k}</button>
                  )
                })}
                {mode === 'use' ? (
                  <>
                    <button className="btn" style={{ color: 'var(--red)' }} onClick={() => {
                      if (confirmMiss === index) { setConfirmMiss(null); pick.advance() }
                      else setConfirmMiss(index)
                    }}>{confirmMiss === index ? '确认都不对？' : '都不对'}</button>
                    {confirmMiss === index && <button className="btn" onClick={() => setConfirmMiss(null)}>取消</button>}
                  </>
                ) : (
                  <>
                    <button className="btn" style={{ color: 'var(--purple)' }} onClick={() => go('lookup')}>都不对 · 我来画</button>
                    <button className="btn" style={{ color: 'var(--amber)' }} onClick={pick.advance}>纠正</button>
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
          <div className="step"><b>输入</b><span>原图+候选图+指标</span></div>
          <div className="step"><b>中间产物</b><span>特征比对结果</span></div>
          <div className="step"><b>输出</b><span>判定 + 分流去向</span></div>
        </div>
      </div>
    </div>
  )
}
