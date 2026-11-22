import type { PageId } from '../App'

export default function RedrawPage({ go }: { go: (id: PageId) => void }) {
  return (
    <>
      <h2>重画 · p004_f01</h2>
      <p className="sub">3 个候选都不是 · 照原图重画，存了直接下一条</p>
      <div className="grid2">
        <div>
          <p className="lab">原图</p>
          <div style={{ height: 180, background: 'var(--panel)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="120" viewBox="0 0 60 40" fill="none" stroke="#5F5E5A" strokeWidth="1.2">
              <polygon points="30,3 50,14 50,29 30,39 10,29 10,14" />
            </svg>
          </div>
        </div>
        <div>
          <p className="lab">你画</p>
          <div style={{ height: 180, border: '1px dashed var(--border)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--faint)' }}>
            结构编辑器待接入
          </div>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <button className="act">保存并重画下一条 →</button>{' '}
        <button className="act" onClick={() => go('review')}>返回审阅</button>
      </div>
    </>
  )
}
