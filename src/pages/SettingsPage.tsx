import { useEffect, useState } from 'react'
import { api, baseUrl, setBaseUrl } from '../api'

export default function SettingsPage() {
  const [url, setUrl] = useState(baseUrl())
  const [mineruKey, setMineruKey] = useState('')
  const [keyState, setKeyState] = useState<{ set: boolean; tail: string }>({ set: false, tail: '' })
  const [message, setMessage] = useState('')

  useEffect(() => {
    api
      .settings()
      .then((s) => setKeyState({ set: s.mineru_key_set, tail: s.mineru_key_tail }))
      .catch(() => setKeyState({ set: false, tail: '' }))
  }, [])

  const saveKey = async () => {
    setMessage('')
    try {
      setBaseUrl(url)
      const saved = await api.saveSettings({ mineru_key: mineruKey })
      setKeyState({ set: saved.mineru_key_set, tail: saved.mineru_key_tail })
      setMineruKey('')
      setMessage(saved.mineru_key_set ? '已保存，下一个任务立即生效' : '已清除 key')
    } catch (error) {
      setMessage((error as Error).message)
    }
  }

  return (
    <>
      <h2>设置</h2>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>本地服务</div>
        <p className="lab">服务地址</p>
        <div className="row">
          <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button
            className="act"
            onClick={async () => {
              setBaseUrl(url)
              try {
                const health = await api.health()
                setMessage(`服务正常 v${health.version}`)
              } catch (error) {
                setMessage((error as Error).message)
              }
            }}
          >
            测试
          </button>
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>MinerU 解析密钥</div>
        <p className="lab">
          {keyState.set ? `已配置 · 尾号 ${keyState.tail}` : '未配置（任务会以 dry-run 运行，只做核验与页处理）'}
        </p>
        <div className="row">
          <input
            type="password"
            placeholder="粘贴 MinerU token"
            value={mineruKey}
            onChange={(e) => setMineruKey(e.target.value)}
          />
          <button className="act" onClick={() => void saveKey()}>保存</button>
        </div>
        <p className="lab" style={{ margin: '8px 0 0' }}>
          存在本机 data/config.json，不上传、不进仓库
        </p>
      </div>

      {message && <p className="sub">{message}</p>}
    </>
  )
}
