import { useEffect, useState } from 'react'
import { baseUrl, probe, setBaseUrl } from '../api'

export default function SettingsPage() {
  const [url, setUrl] = useState(baseUrl())
  const [status, setStatus] = useState('')
  const [testing, setTesting] = useState(false)

  useEffect(() => { setUrl(baseUrl()) }, [])

  const save = async (value: string) => {
    const v = value.trim().replace(/\/$/, '')
    if (!/^https?:\/\//.test(v)) { setStatus('地址要以 http:// 或 https:// 开头'); return }
    setBaseUrl(v)
    setUrl(v)
    setTesting(true)
    setStatus('正在连接…')
    const ok = await probe()
    setTesting(false)
    setStatus(ok ? `已连接：${v}` : `连不上：${v}（检查后端是否启动、地址是否正确）`)
  }

  return (
    <div className="page on">
      <h1 className="title">设置</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 12 }}>后端连接</div>
        <div className="field">
          <label title="后端服务地址，改完自动测试连接">后端地址</label>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8765" />
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'center' }}>
          <button className="btn pri" disabled={testing} onClick={() => void save(url)}>
            {testing ? '测试中…' : '保存并测试'}
          </button>
          <button className="btn" onClick={() => void save('http://127.0.0.1:8765')}>恢复默认</button>
        </div>
        {status && <div style={{ color: status.startsWith('已连接') ? '#1a7a3c' : 'var(--muted)', marginTop: 10 }}>{status}</div>}
        <div style={{ color: 'var(--muted)', marginTop: 12, fontSize: 12, lineHeight: 1.7 }}>
          演示机上后端默认在 127.0.0.1:8765；如果后端部署在别的机器，填那台机器的地址。
        </div>
      </div>
    </div>
  )
}
