import { useState } from 'react'
import type { Mode } from './types'
import { STORAGE_KEYS } from './types'
import ConnectPage from './pages/ConnectPage'
import TasksPage from './pages/TasksPage'
import NewTaskPage from './pages/NewTaskPage'
import ScreenPage from './pages/ScreenPage'
import ReviewPage from './pages/ReviewPage'
import RedrawPage from './pages/RedrawPage'
import ReportPage from './pages/ReportPage'
import SettingsPage from './pages/SettingsPage'

export type PageId = 'connect' | 'tasks' | 'new' | 'screen' | 'review' | 'redraw' | 'report' | 'settings'

const NAV: { id: PageId; label: string; trainOnly?: boolean }[] = [
  { id: 'connect', label: '1 连接' },
  { id: 'tasks', label: '2 任务' },
  { id: 'new', label: '3 新建' },
  { id: 'screen', label: '4 结构式筛选', trainOnly: true },
  { id: 'review', label: '5 审阅' },
  { id: 'report', label: '6 报告' },
  { id: 'settings', label: '7 设置' },
]

export default function App() {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem(STORAGE_KEYS.mode)
    return saved === 'use' || saved === 'train' ? saved : 'train'
  })
  const [page, setPage] = useState<PageId>('connect')

  const go = (id: PageId) => {
    if (mode === 'use' && id === 'screen') return
    setPage(id)
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    localStorage.setItem(STORAGE_KEYS.mode, m)
    if (m === 'use' && page === 'screen') setPage('tasks')
  }

  const pages: Record<PageId, React.ReactNode> = {
    connect: <ConnectPage />,
    tasks: <TasksPage go={go} />,
    new: <NewTaskPage />,
    screen: <ScreenPage />,
    review: <ReviewPage go={go} />,
    redraw: <RedrawPage go={go} />,
    report: <ReportPage mode={mode} />,
    settings: <SettingsPage />,
  }

  return (
    <>
      <div className="top">
        <div className="logo">C</div>
        <span className="top-title">CSD</span>
        <span className="lab" style={{ margin: 0 }}>界面原型</span>
        <div className="mode">
          <button className={mode === 'use' ? 'on' : ''} onClick={() => switchMode('use')}>使用模式</button>
          <button className={mode === 'train' ? 'on' : ''} onClick={() => switchMode('train')}>训练模式</button>
        </div>
      </div>
      <div className="nav">
        {NAV.filter((n) => !(mode === 'use' && n.trainOnly)).map((n) => (
          <button key={n.id} className={page === n.id ? 'on' : ''} onClick={() => go(n.id)}>{n.label}</button>
        ))}
      </div>
      <div className="page">{pages[page]}</div>
    </>
  )
}
