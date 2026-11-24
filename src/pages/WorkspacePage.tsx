import { useEffect, useState } from 'react'
import { api } from '../api'
import { ensureWritePermission, loadDirHandle, pickDirectory, saveDirHandle } from '../updater'

export default function WorkspacePage() {
  const [dataDir, setDataDir] = useState('')
  const [chosen, setChosen] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.health().then((h) => setDataDir(h.data_dir || '')).catch(() => setDataDir('后端未连接'))
    loadDirHandle().then((d) => { if (d) setChosen(d.name) }).catch(() => {})
  }, [])

  const choose = async () => {
    try {
      let dir = await loadDirHandle()
      if (!dir || !(await ensureWritePermission(dir))) { dir = await pickDirectory(); await saveDirHandle(dir) }
      setChosen(dir.name)
      setMsg(`已选工作区「${dir.name}」。换工作区后若里面没有原数据，需重新识别文献。`)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      setMsg(`选择失败：${String(e instanceof Error ? e.message : e)}`)
    }
  }

  return (
    <div className="page on">
      <h1 className="title">工作区</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>当前工作区</div>
        <div className="field">
          <label title="后端数据下载、存储的位置">后端数据目录</label>
          <input readOnly value={dataDir} />
        </div>
        {chosen && <div className="field" style={{ marginTop: 10 }}><label>本地引导目录</label><input readOnly value={chosen} /></div>}
      </div>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>更换工作区</div>
        <div className="field" style={{ maxWidth: 360 }}>
          <label title="换文件夹后若没有原数据，需重新下载/识别">授权另一个文件夹</label>
          <button className="btn" onClick={() => void choose()}>选择文件夹…</button>
        </div>
        {msg && <div style={{ color: 'var(--muted)', marginTop: 10 }}>{msg}</div>}
      </div>
      <div className="devpanel">
        <b>工作区初始化这一步</b>
        <div className="steps">
          <div className="step"><b>输入</b><span>用户选的文件夹</span></div>
          <div className="step"><b>中间产物</b><span>API 授权句柄</span></div>
          <div className="step"><b>输出</b><span>数据落点目录</span></div>
        </div>
      </div>
    </div>
  )
}
