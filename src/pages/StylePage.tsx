import Drawer from '../ui/Drawer'
import MolSvg from '../ui/MolSvg'

type Mol = { id: number }
const ITEMS: Mol[] = Array.from({ length: 10 }, (_, i) => ({ id: i }))
const FRAMES = ['现代', 'A', 'B', 'C', 'D', 'E']

export default function StylePage() {
  return (
    <div className="page on">
      <h1 className="title">风格评审</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>风格参照 · 用户上传</div>
        <div className="refbar">
          {['现代', '参照 A', '参照 B', '参照 C', '参照 D', '参照 E'].map((e, k) => (
            <div className={`frame ${k === 0 ? 'modern' : ''}`} key={e}>
              <div className="lab">{e}</div>
              <MolSvg color={k === 0 ? '#0f6e56' : '#185fa5'} />
            </div>
          ))}
        </div>
      </div>
      <Drawer
        items={ITEMS}
        windowSec={4}
        renderItem={(_item, index, pick) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>分子 {index + 1}</div>
            <div className="series">
              {FRAMES.map((e, k) => {
                const marked = pick.saved.indexOf(k) >= 0
                return (
                  <div className={`frame pick ${k === 0 ? 'modern' : ''} ${marked ? 'marked' : ''}`} key={e} onClick={() => pick.toggle(k)}>
                    <div className="lab">{e}</div>
                    <MolSvg color={k === 0 ? '#0f6e56' : '#185fa5'} />
                  </div>
                )
              })}
            </div>
          </>
        )}
      />
    </div>
  )
}
