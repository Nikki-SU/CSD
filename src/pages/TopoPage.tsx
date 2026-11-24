import Drawer from '../ui/Drawer'
import { api } from '../api'
import { useJobData, type Figure } from '../useJob'

const METRICS = ['环数', '环大小', '标签']
const OPTIONS: Record<string, string[]> = {
  '环数': ['0', '1', '2', '3', '4'],
  '环大小': ['5', '6', '6,5', '其它'],
  '标签': ['无', 'N', 'N O', 'N O S'],
}

export default function TopoPage() {
  const { job, figures, loading } = useJobData()

  const save = (fig: Figure, feature: string, expected: string) => {
    if (!job) return
    void api.saveTopo({ job_id: job.job_id, rows: [{ figure_id: fig.figure_id, feature, expected, detected: '' }] })
  }

  if (loading) return <div className="page on"><h1 className="title">拓扑标注</h1><div className="card">加载中…</div></div>
  if (!job || !figures.length) return <div className="page on"><h1 className="title">拓扑标注</h1><div className="card">暂无可标注的图。先去「新建任务」识别结构式。</div></div>

  return (
    <div className="page on">
      <h1 className="title">拓扑标注</h1>
      <Drawer
        items={figures}
        windowSec={4}
        renderItem={(fig, _index, pick) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>{fig.article} · 第{fig.page}页</div>
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
              <div style={{ width: 150 }}>
                <img src={api.fileUrl(job.job_id, fig.image)} alt={fig.figure_id} style={{ width: '100%', objectFit: 'contain' }} />
              </div>
              <div style={{ flex: 1 }}>
                {METRICS.map((m, mi) => (
                  <div key={m} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 4 }}>{m}</div>
                    <div className="row" style={{ gap: 6 }}>
                      {OPTIONS[m].map((opt, oi) => {
                        const k = mi * 10 + oi
                        const marked = pick.saved.indexOf(k) >= 0
                        return (
                          <button key={opt} className={`btn pick ${marked ? 'marked' : ''}`}
                            onClick={() => { pick.toggle(k); save(fig, m, opt) }}>{opt}</button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      />
    </div>
  )
}
