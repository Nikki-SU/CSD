import { useCallback, useEffect, useState } from 'react'
import type { Mode } from './types'
import { STORAGE_KEYS } from './types'
import { api, probe } from './api'
import { registerNav } from './nav'
import BootstrapGuide from './BootstrapGuide'
import { BUNDLE_VERSION } from './bootstrapFiles'
import {
  applyUpdate, backendOutdated, bundleApplied, ensureWritePermission,
  isOutdated, loadDirHandle, markBundleApplied, pickDirectory, saveDirHandle,
} from './updater'
import WorkspacePage from './pages/WorkspacePage'
import NewTaskPage from './pages/NewTaskPage'
import ReviewPage from './pages/ReviewPage'
import ReportPage from './pages/ReportPage'
import ScreenPage from './pages/ScreenPage'
import StylePage from './pages/StylePage'
import TopoPage from './pages/TopoPage'
import DiagPage from './pages/DiagPage'
import LookupPage from './pages/LookupPage'
import SettingsPage from './pages/SettingsPage'

export type PageId = 'work' | 'new' | 'review' | 'report' | 'screen' | 'style' | 'topo' | 'diag' | 'lookup' | 'settings'

type NavItem = { id: PageId; label: string }

const WORK_NAV: NavItem[] = [
  { id: 'new', label: '新建任务' },
  { id: 'review', label: '审阅' },
  { id: 'report', label: '报告' },
]
const TRAIN_NAV: NavItem[] = [
  { id: 'screen', label: '结构式筛选' },
  { id: 'style', label: '风格评审' },
  { id: 'topo', label: '拓扑标注' },
  { id: 'diag', label: '归因对比' },
]

type Versions = { frontend: number; backend: number; model: number; data: number }

export default function App() {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem(STORAGE_KEYS.mode)
    return saved === 'train' ? 'train' : 'use'
  })
  const [dev, setDev] = useState(false)
  const [page, setPage] = useState<PageId>('new')
  const [backendUp, setBackendUp] = useState(false)
  const [versions, setVersions] = useState<Versions | null>(null)
  const [updating, setUpdating] = useState(false)
  const [updateMsg, setUpdateMsg] = useState('')
  const [needRefresh, setNeedRefresh] = useState(false)

  // 后端探测：在线后拉版本，用于本地后端更新判断
  const boot = useCallback(async () => {
    const ok = await probe()
    setBackendUp(ok)
    if (!ok) return
    try {
      const h = await api.health() as { versions?: Versions }
      if (h.versions) setVersions(h.versions)
    } catch { /* 老后端没有 versions 字段，安静跳过 */ }
  }, [])

  useEffect(() => { void boot() }, [boot])
  useEffect(() => {
    const t = window.setInterval(() => { void boot() }, 3000)
    return () => window.clearInterval(t)
  }, [boot])

  // 前端更新探测：no-store 拉 version.json，线上比页面编译时新 → 提示刷新
  useEffect(() => {
    let alive = true
    const check = async () => {
      try {
        const res = await fetch(`version.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok) return
        const v = await res.json() as { frontend?: number }
        if (alive && typeof v.frontend === 'number' && v.frontend > BUNDLE_VERSION.frontend) setNeedRefresh(true)
      } catch { /* 探测失败安静跳过 */ }
    }
    void check()
    const t = window.setInterval(() => { void check() }, 60_000)
    return () => { alive = false; window.clearInterval(t) }
  }, [])

  // 本地后端版本落后 → 用户点按钮写新文件（File System Access 需点击授权）
  const onUpdateBackend = async () => {
    setUpdating(true); setUpdateMsg('正在写入本地文件…')
    try {
      let dir = await loadDirHandle()
      if (!dir || !(await ensureWritePermission(dir))) { dir = await pickDirectory(); await saveDirHandle(dir) }
      const res = await applyUpdate(dir)
      const stale = res.launcherStale.length
        ? `；启动器有更新（${res.launcherStale.join('、')}），请到引导页重新写入覆盖`
        : ''
      markBundleApplied()
      setUpdateMsg(`已更新 ${res.changed} 个文件${stale}。请关掉后端黑窗口再双击 start-windows.bat 重启。`)
    } catch (e) {
      setUpdateMsg(`更新失败：${String(e instanceof Error ? e.message : e)}`)
    } finally { setUpdating(false) }
  }

  const go = (id: PageId) => {
    if (['screen', 'style', 'topo', 'diag', 'lookup'].includes(id) && mode === 'use') {
      setMode('train')
      localStorage.setItem(STORAGE_KEYS.mode, 'train')
    }
    setPage(id)
  }
  useEffect(() => { registerNav(go) }, [page, mode])

  const switchMode = (m: Mode) => {
    setMode(m)
    localStorage.setItem(STORAGE_KEYS.mode, m)
    if (m === 'use') {
      setDev(false)
      if (page === 'screen' || page === 'style' || page === 'topo' || page === 'diag' || page === 'lookup') setPage('new')
    }
  }

  // 后端离线 → 引导部署（设置页例外，允许改后端地址）
  if (!backendUp && page !== 'settings') {
    return <div className="main"><BootstrapGuide onRetry={() => void boot()} /></div>
  }

  const backendBehind = versions && backendOutdated(versions) && !bundleApplied()
  const frontendBehind = isOutdated({ frontend: versions?.frontend ?? BUNDLE_VERSION.frontend }) && needRefresh

  const pages: Record<PageId, React.ReactNode> = {
    work: <WorkspacePage />,
    new: <NewTaskPage />,
    review: <ReviewPage mode={mode} go={go} />,
    report: <ReportPage />,
    screen: <ScreenPage />,
    style: <StylePage />,
    topo: <TopoPage />,
    diag: <DiagPage />,
    lookup: <LookupPage />,
    settings: <SettingsPage />,
  }

  return (
    <div className={`app ${dev ? 'devon' : ''}`}>
      {(backendBehind || frontendBehind || updateMsg) && (
        <div style={{ background: '#fff4d6', borderBottom: '1px solid #e0c060', padding: '8px 16px', fontSize: 13, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          {frontendBehind && <span>页面有新版本，<button className="btn" onClick={() => location.reload()}>点此刷新</button></span>}
          {backendBehind && !updateMsg && (
            <span>本地后端有新版本（{versions?.backend} → {BUNDLE_VERSION.backend}），
              <button className="btn pri" disabled={updating} onClick={() => void onUpdateBackend()}>{updating ? '更新中…' : '一键更新本地文件'}</button>
            </span>
          )}
          {updateMsg && <span>{updateMsg}</span>}
        </div>
      )}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <aside className="side">
          <div className="seg small" style={{ marginBottom: 14 }}>
            <button className={mode === 'use' ? 'on' : ''} onClick={() => switchMode('use')}>使用</button>
            <button className={mode === 'train' ? 'on' : ''} onClick={() => switchMode('train')}>训练</button>
          </div>
          {mode === 'train' && (
            <label className="side-dev">
              开发者模式
              <input type="checkbox" checked={dev} onChange={(e) => setDev(e.target.checked)} />
            </label>
          )}
          <div className="navgrp">工作</div>
          {WORK_NAV.map((n) => (
            <button key={n.id} className={`nav ${page === n.id ? 'on' : ''}`} onClick={() => go(n.id)}>{n.label}</button>
          ))}
          {mode === 'train' && (
            <>
              <div className="navgrp">训练</div>
              {TRAIN_NAV.map((n) => (
                <button key={n.id} className={`nav ${page === n.id ? 'on' : ''}`} onClick={() => go(n.id)}>{n.label}</button>
              ))}
            </>
          )}
          <div className="navgrp">系统</div>
          <button className={`nav ${page === 'settings' ? 'on' : ''}`} onClick={() => go('settings')}>设置</button>
        </aside>
        <div className="main">{pages[page]}</div>
      </div>
    </div>
  )
}
