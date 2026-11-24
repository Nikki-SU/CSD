import { useEffect, useRef, useState } from 'react'
import { api, type JobItem } from '../api'

type Figure = {
  figure_id: string
  image: string
  article: string
  page: number
  conf: number
  has_structure?: boolean | null
}

const PER_GROUP = 100

export default function ScreenPage() {
  const [job, setJob] = useState<JobItem | null>(null)
  const [figures, setFigures] = useState<Figure[]>([])
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  const [group, setGroup] = useState(1)
  const [showNext, setShowNext] = useState(false)
  const [message, setMessage] = useState('')
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const { jobs } = await api.jobs()
        const target = [...jobs].reverse().find((j) => j.status !== 'queued')
        if (!alive || !target) { if (alive) setMessage('还没有任务。先去「新建任务」提交文件夹。'); return }
        setJob(target)
        const poll = async () => {
          const cur = await api.job(target.job_id)
          if (!alive) return
          setJob(cur)
          if (cur.status === 'running' || cur.status === 'queued') {
            setMessage(cur.progress?.message || '识别中…')
            setTimeout(() => void poll(), 1500)
            return
          }
          try {
            const f = await api.figures(target.job_id)
            if (f?.figures?.length) setFigures(f.figures)
            else setMessage('这个任务没有结构式图（可能没检出，或不是文件夹任务）')
          } catch {
            setMessage('结果还没生成')
          }
        }
        void poll()
      } catch (e) {
        if (alive) setMessage(String((e as Error).message || e))
      }
    }
    void load()
    return () => { alive = false }
  }, [])

  const visible = figures.filter((f) => !removed.has(f.figure_id))
  const groupItems = visible.slice((group - 1) * PER_GROUP, group * PER_GROUP)
  const kept = visible.length
  const cut = removed.size

  const checkBottom = () => {
    const s = scroller.current
    if (s && s.scrollTop + s.clientHeight >= s.scrollHeight - 120 && group * PER_GROUP < visible.length) setShowNext(true)
  }
  const remove = (id: string) => {
    setRemoved((prev) => new Set(prev).add(id))
    if (job) {
      void api.saveLabels({ job_id: job.job_id, rows: [{ figure_id: id, has_structure: false }] }).catch(() => {})
    }
  }
  const nextGroup = () => {
    setGroup((g) => g + 1)
    setShowNext(false)
    if (scroller.current) scroller.current.scrollTop = 0
  }

  return (
    <div className="page on">
      <h1 className="title">结构式筛选</h1>
      <div className="card screen-card">
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 14 }}>
          <div>第 {group} 组</div>
          <div style={{ marginLeft: 'auto', color: 'var(--muted)' }}>保留 <b>{kept}</b> · 剔除 <b>{cut}</b></div>
        </div>
        {message && <div style={{ color: 'var(--muted)', marginBottom: 10 }}>{message}</div>}
        <div className="wf-scroll" ref={scroller} onScroll={checkBottom} onWheel={checkBottom} onTouchMove={checkBottom}>
          <div className="wf">
            {groupItems.map((f) => (
              <div key={f.figure_id} className="tile" title={`${f.article} 第${f.page}页 置信度${f.conf}`} onClick={() => remove(f.figure_id)}>
                {job ? <img src={api.fileUrl(job.job_id, f.image)} alt={f.figure_id} /> : null}
              </div>
            ))}
          </div>
        </div>
        {showNext && <div className="nextgroup" style={{ display: 'block' }}><button className="btn pri" onClick={nextGroup}>下一组 →</button></div>}
        <div className="devpanel">
          <b>瀑布流这一步</b>
          <div className="steps">
            <div className="step"><b>输入</b><span>文件夹任务经 MolDet 串行识别的图片合集</span></div>
            <div className="step"><b>中间产物</b><span>逐张结构式裁图（带文章/页/置信度）</span></div>
            <div className="step"><b>输出</b><span>人工剔除后的干净结构式图集（回流训练）</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
