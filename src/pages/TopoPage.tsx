import Drawer from '../ui/Drawer'
import MolSvg from '../ui/MolSvg'

type Fig = { id: number }
const ITEMS: Fig[] = Array.from({ length: 10 }, (_, i) => ({ id: i }))
const METRICS = ['环数', '环大小', '标签']

export default function TopoPage() {
  return (
    <div className="page on">
      <h1 className="title">拓扑标注</h1>
      <Drawer
        items={ITEMS}
        windowSec={4}
        renderItem={(_item, index, pick) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>图 {index + 1}</div>
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
              <div style={{ width: 150 }}><MolSvg color="#26241f" /></div>
              <div className="row" style={{ gap: 8, flex: 1 }}>
                {METRICS.map((m, k) => (
                  <button key={m} className={`btn pick ${pick.saved.indexOf(k) >= 0 ? 'marked' : ''}`} onClick={() => pick.toggle(k)}>
                    {m}<br /><b>{k === 0 ? '1' : k === 1 ? '6' : 'N O'}</b>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      />
    </div>
  )
}
