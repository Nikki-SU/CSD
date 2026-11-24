import { useState } from 'react'
import type { Mode } from './types'
import { STORAGE_KEYS } from './types'
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

type NavItem = { id: PageId; label: string; trainOnly?: boolean }

const WORK_NAV: NavItem[] = [
  { id: 'work', label: '工作区' },
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

export default function App() {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem(STORAGE_KEYS.mode)
    return saved === 'train' ? 'train' : 'use'
  })
  const [dev, setDev] = useState(false)
  const [page, setPage] = useState<PageId>('work')

  const go = (id: PageId) => setPage(id)
  const switchMode = (m: Mode) => {
    setMode(m)
    localStorage.setItem(STORAGE_KEYS.mode, m)
    if (m === 'use') {
      setDev(false)
      if (page === 'screen' || page === 'style' || page === 'topo' || page === 'diag' || page === 'lookup') setPage('work')
    }
  }

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
  )
}
