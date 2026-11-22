import type { PageId } from '../App'
import { MOCK_JOBS } from '../mock'

export default function TasksPage({ go }: { go: (id: PageId) => void }) {
  return (
    <>
      <h2>任务</h2>
      {MOCK_JOBS.map((job) => (
        <div className="card between" key={job.job_id}>
          <div>
            <div className="mono" style={{ fontSize: 13 }}>{job.job_id}</div>
            <p className="lab" style={{ margin: '4px 0 0' }}>
              {job.created_at.slice(0, 16).replace('T', ' ')} · {job.source_type === 'pdf' ? 'PDF' : '图片'}
              {job.figures ? ` · ${job.figures} 页` : ''}
            </p>
          </div>
          <div className="row">
            {job.status === 'running' && <span className="info" style={{ fontSize: 12 }}>精判 {job.progress}%</span>}
            {job.status === 'done' && <span className="ok" style={{ fontSize: 12 }}>完成</span>}
            {job.status === 'failed' && <span className="danger" style={{ fontSize: 12 }}>失败</span>}
            {job.status === 'running' && <button className="act" onClick={() => go('review')}>审阅</button>}
            {job.status === 'done' && <button className="act" onClick={() => go('report')}>报告</button>}
            {job.status === 'failed' && <button className="act">日志</button>}
          </div>
        </div>
      ))}
    </>
  )
}
