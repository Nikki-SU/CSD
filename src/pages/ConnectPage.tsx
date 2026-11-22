import { useState } from 'react'
import { STORAGE_KEYS } from '../types'

export default function ConnectPage() {
  const [pat, setPat] = useState(() => localStorage.getItem(STORAGE_KEYS.pat) ?? '')
  const [owner, setOwner] = useState(() => localStorage.getItem(STORAGE_KEYS.owner) ?? 'Nikki-SU')
  const [repo, setRepo] = useState(() => localStorage.getItem(STORAGE_KEYS.repo) ?? 'CSDws')
  const [branch, setBranch] = useState(() => localStorage.getItem(STORAGE_KEYS.branch) ?? 'main')

  const save = () => {
    localStorage.setItem(STORAGE_KEYS.pat, pat)
    localStorage.setItem(STORAGE_KEYS.owner, owner)
    localStorage.setItem(STORAGE_KEYS.repo, repo)
    localStorage.setItem(STORAGE_KEYS.branch, branch)
  }

  return (
    <>
      <h2>连接工作库</h2>
      <p className="sub">首次进入 · 只保存在这台设备</p>
      <div className="card">
        <p className="lab">Personal access token</p>
        <input type="password" placeholder="粘贴 token" value={pat} onChange={(e) => setPat(e.target.value)} />
      </div>
      <div className="grid3" style={{ marginBottom: 14 }}>
        <div>
          <p className="lab">Owner</p>
          <input type="text" value={owner} onChange={(e) => setOwner(e.target.value)} />
        </div>
        <div>
          <p className="lab">Repo</p>
          <input type="text" value={repo} onChange={(e) => setRepo(e.target.value)} />
        </div>
        <div>
          <p className="lab">Branch</p>
          <input type="text" value={branch} onChange={(e) => setBranch(e.target.value)} />
        </div>
      </div>
      <button className="act" onClick={save}>连接</button>
    </>
  )
}
