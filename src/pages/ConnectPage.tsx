import { useEffect, useState } from 'react'
import { api, baseUrl, setBaseUrl } from '../api'

export default function ConnectPage() {
  const [url, setUrl] = useState(baseUrl())
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle')
  const [info, setInfo] = useState('')

  const test = async (target: string) => {
    setBaseUrl(target)
    setState('idle')
    setInfo('连接中…')
    try {
      const health = await api.health()
      setState('ok')
      setInfo(`v${health.version} · ${health.data_dir}`)
    } catch (error) {
      setState('fail')
      setInfo((error as Error).message)
    }
  }

  useEffect(() => {
    void test(baseUrl())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      <h2>连接本地服务</h2>
      <p className="sub">后端跑在这台机器上，地址只保存在本机浏览器</p>
      <div className="card">
        <p className="lab">服务地址</p>
        <div className="row">
          <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8765" />
          <button className="act" onClick={() => void test(url)}>测试连接</button>
        </div>
        {state === 'ok' && <p className="ok" style={{ margin: '8px 0 0' }}>已连接 · {info}</p>}
        {state === 'fail' && <p className="danger" style={{ margin: '8px 0 0' }}>{info}</p>}
      </div>
      <p className="lab">启动命令：python -m backend.server（局域网加 --lan）</p>
    </>
  )
}
