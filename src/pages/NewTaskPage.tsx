import { useState } from 'react'

export default function NewTaskPage() {
  const [pathMode, setPathMode] = useState(false)
  const [srcStyle, setSrcStyle] = useState('pdf')
  const [imgStyle, setImgStyle] = useState('按文件名年份推断')
  const [runMode, setRunMode] = useState('只跑二值')

  return (
    <>
      <h2>新建任务</h2>
      <div className="grid2">
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 10 }}>文献 PDF</div>
          <div style={{ border: '1px dashed var(--border)', borderRadius: 6, padding: 22, textAlign: 'center', color: 'var(--muted)' }}>
            拖入 PDF · ≤ 100 MB
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <p className="lab" style={{ margin: 0 }}>风格</p>
            <select value={srcStyle} onChange={(e) => setSrcStyle(e.target.value)}>
              <option value="pdf">自动识别 · 可改</option>
            </select>
          </div>
          <button className="act" style={{ marginTop: 12, width: '100%' }}>提交任务</button>
        </div>

        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 10 }}>结构式图片 / 批量路径</div>
          <div style={{ border: '1px dashed var(--border)', borderRadius: 6, padding: 16, textAlign: 'center', color: 'var(--muted)' }}>
            拖入 PNG / JPG · 可多张
          </div>
          <div style={{ marginTop: 10 }}>
            <p className="lab" style={{ margin: '0 0 5px' }}>或指定路径（批量导入 → 瀑布流）</p>
            <div className="row">
              <input type="text" placeholder="粘贴目录路径" disabled={!pathMode} />
              <button className="act" onClick={() => setPathMode(!pathMode)}>{pathMode ? '取消' : '选文件夹'}</button>
            </div>
            <p className="lab" style={{ margin: '5px 0 0' }}>私库路径可直读；本机目录需授权</p>
          </div>
          <div style={{ marginTop: 12 }}>
            <p className="lab" style={{ margin: '0 0 5px' }}>风格</p>
            <select value={imgStyle} onChange={(e) => setImgStyle(e.target.value)}>
              <option>按文件名年份推断</option>
              <option>试探多个年代，取效果最好</option>
              <option>default_1970s</option>
              <option>default_1980s</option>
              <option>default_1960s</option>
              <option>default_1950s</option>
            </select>
          </div>
          <div style={{ marginTop: 12 }}>
            <p className="lab" style={{ margin: '0 0 5px' }}>跑几种模式</p>
            {['只跑二值', '只跑精确', '两种都跑（对照）'].map((m) => (
              <span key={m} className={`pill ${runMode === m ? 'on' : ''}`} onClick={() => setRunMode(m)}>{m}</span>
            ))}
          </div>
          <button className="act" style={{ marginTop: 12, width: '100%' }}>提交任务</button>
        </div>
      </div>
    </>
  )
}
