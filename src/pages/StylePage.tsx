import Drawer from '../ui/Drawer'
import { api } from '../api'
import { useJobData, type Figure } from '../useJob'

// 风格评审 = 渲染抽检：同一分子的现代形式 + 各年代横排对比，点格标"画得好/不好"。
// 顶部参照条与下面分子条同列宽一一对应。
const FRAMES = ['现代', '1937', '1948', '1960', '1971', '1980']

export default function StylePage() {
  const { job, figures, loading } = useJobData()

  const mark = (fig: Figure, ok: boolean) => {
    if (!job) return Promise.resolve()
    return api.saveLabels({ job_id: job.job_id, rows: [{ figure_id: fig.figure_id, verdict: ok ? 'style_ok' : 'style_bad' }] })
  }

  if (loading) return <div className="page on"><h1 className="title">风格评审</h1><div className="card">加载中…</div></div>
  if (!job || !figures.length) return <div className="page on"><h1 className="title">风格评审</h1><div className="card">暂无可评审的图。先去「新建任务」识别结构式。</div></div>

  return (
    <div className="page on">
      <h1 className="title">风格评审</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>风格参照 · 真实各年代图（{figures.length} 张待评）</div>
        <div className="refbar">
          {FRAMES.map((e, k) => (
            <div className={`frame ${k === 0 ? 'modern' : ''}`} key={e}>
              <div className="lab">{e}</div>
              <img src={api.fileUrl(job.job_id, figures[k % figures.length].image)} alt={e} style={{ width: '100%', height: 56, objectFit: 'contain' }} />
            </div>
          ))}
        </div>
      </div>
      <Drawer
        items={figures}
        windowSec={4}
        renderItem={(fig, _index, pick) => (
          <>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>{fig.article} · 第{fig.page}页</div>
            <div className="series">
              {FRAMES.map((e, k) => {
                const marked = pick.saved.indexOf(k) >= 0
                return (
                  <div className={`frame pick ${k === 0 ? 'modern' : ''} ${marked ? 'marked' : ''}`} key={e}
                    onClick={() => { pick.toggle(k); void mark(fig, !marked) }}>
                    <div className="lab">{e}</div>
                    <img src={api.fileUrl(job.job_id, fig.image)} alt={e} style={{ width: '100%', height: 56, objectFit: 'contain' }} />
                  </div>
                )
              })}
            </div>
          </>
        )}
      />
    </div>
  )
}
