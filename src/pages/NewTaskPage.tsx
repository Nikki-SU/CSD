import { useState } from 'react'

export default function NewTaskPage() {
  const [source, setSource] = useState<'pdf' | 'image' | 'folder'>('pdf')
  return (
    <div className="page on">
      <h1 className="title">新建任务</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 12 }}>来源</div>
        <div className="seg" style={{ marginBottom: 14 }}>
          <button className={source === 'pdf' ? 'on' : ''} onClick={() => setSource('pdf')}>文献 PDF</button>
          <button className={source === 'image' ? 'on' : ''} onClick={() => setSource('image')}>结构式图片</button>
          <button className={source === 'folder' ? 'on' : ''} onClick={() => setSource('folder')}>文件夹路径</button>
        </div>
        {source === 'folder' ? (
          <div className="field">
            <label title="里面的 PDF 逐个解析；数据仍存在工作区">文件夹路径</label>
            <input defaultValue="F:\文献批量下载\pdfs" />
          </div>
        ) : (
          <div style={{ border: '1px dashed var(--line)', borderRadius: 8, padding: 22, textAlign: 'center', color: 'var(--muted)' }}>
            拖入{source === 'pdf' ? ' PDF · 可多张' : ' PNG/JPG · 可批量'}
          </div>
        )}
        <div className="field" style={{ marginTop: 14 }}>
          <label>风格</label>
          <select defaultValue="auto">
            <option value="auto">自动识别（可改）</option>
            <option value="manual">手动首选</option>
            <option value="filename">按文件名年份推断</option>
            <option value="probe">试探多个年代</option>
          </select>
        </div>
        <div className="field" style={{ marginTop: 14, maxWidth: 280 }}>
          <label>运行模式</label>
          <select defaultValue="binary">
            <option value="binary">二值剪枝</option>
            <option value="exact">精确剪枝</option>
            <option value="both">两种都跑</option>
          </select>
        </div>
        <div style={{ marginTop: 16 }}><button className="btn pri">提交任务</button></div>
      </div>
    </div>
  )
}
