import { useState } from 'react'
import type { PageId } from '../App'
import { api } from '../api'

interface ScanItem {
  name: string
  path: string
  size: number
  kind: string
  year: number | null
}

const LAST_DIR = 'csd.lastDir'

export default function NewTaskPage({ go }: { go: (id: PageId) => void }) {
  const [dir, setDir] = useState(() => localStorage.getItem(LAST_DIR) ?? '')
  const [items, setItems] = useState<ScanItem[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const scan = async () => {
    setBusy(true)
    setMessage('扫描中…')
    try {
      const data = await api.scan(dir)
      setItems(data.items)
      setPicked(new Set(data.items.map((it) => it.path)))
      localStorage.setItem(LAST_DIR, dir)
      setMessage(`找到 ${data.count} 个文件`)
    } catch (error) {
      setItems([])
      setPicked(new Set())
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggle = (path: string) => {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const submit = async () => {
    if (picked.size === 0) return
    setBusy(true)
    setMessage('提交中…')
    const chosen = items.filter((it) => picked.has(it.path))
    const pdfs = chosen.filter((it) => it.kind === 'pdf').map((it) => it.path)
    const images = chosen.filter((it) => it.kind === 'image').map((it) => it.path)
    try {
      let created = 0
      if (pdfs.length) created += (await api.createBatch(pdfs, 'pdf')).created
      if (images.length) created += (await api.createBatch(images, 'image')).created
      setMessage(`已创建 ${created} 个任务`)
      go('tasks')
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h2>新建任务</h2>
      <p className="sub">选择本机目录，后端直接读取，不上传</p>

      <div className="card">
        <p className="lab">目录路径</p>
        <div className="row">
          <input
            type="text"
            placeholder="例如 D:\\文献批量下载\\pdfs"
            value={dir}
            onChange={(e) => setDir(e.target.value)}
          />
          <button className="act" disabled={busy || !dir.trim()} onClick={() => void scan()}>扫描</button>
        </div>
        {message && <p className="sub" style={{ margin: '8px 0 0' }}>{message}</p>}
      </div>

      {items.length > 0 && (
        <div className="card">
          <div className="between" style={{ marginBottom: 8 }}>
            <span className="lab">已选 {picked.size} / {items.length}</span>
            <span className="row">
              <button className="act" onClick={() => setPicked(new Set(items.map((it) => it.path)))}>全选</button>
              <button className="act" onClick={() => setPicked(new Set())}>清空</button>
            </span>
          </div>
          <div style={{ maxHeight: 340, overflowY: 'auto' }}>
            {items.map((item) => (
              <label key={item.path} className="between" style={{ padding: '6px 0', borderTop: '1px solid var(--border)' }}>
                <span className="row">
                  <input type="checkbox" checked={picked.has(item.path)} onChange={() => toggle(item.path)} />
                  <span className="mono" style={{ fontSize: 12 }}>{item.name}</span>
                </span>
                <span className="lab">
                  {item.year ?? '年份?'} · {(item.size / 1024 / 1024).toFixed(1)} MB
                </span>
              </label>
            ))}
          </div>
          <button className="act" style={{ marginTop: 12, width: '100%' }} disabled={busy || picked.size === 0} onClick={() => void submit()}>
            提交 {picked.size} 个任务
          </button>
        </div>
      )}
    </>
  )
}
