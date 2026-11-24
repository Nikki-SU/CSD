import MolSvg from '../ui/MolSvg'

export default function DiagPage() {
  return (
    <div className="page on">
      <h1 className="title">归因对比</h1>
      <div className="card">
        <table>
          <thead><tr><th>模式</th><th title="分母为已审图数">拓扑准确率</th><th>hit@1</th><th>hit@3</th></tr></thead>
          <tbody>
            <tr><td>二值</td><td>—</td><td>—</td><td>—</td></tr>
            <tr><td>精确</td><td>—</td><td>—</td><td>—</td></tr>
          </tbody>
        </table>
      </div>
      <div className="seg"><button className="on">拓扑不准</button><button>图匹配不准</button></div>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="row">
          <div style={{ width: 120 }}><MolSvg color="#185fa5" /></div>
          <div className="row" style={{ gap: 8, flex: 1 }}>
            <div className="step">环数 1</div>
            <div className="step" style={{ background: 'var(--red-bg)', color: 'var(--red)' }}>环大小 错</div>
            <div className="step">标签 N O</div>
          </div>
        </div>
      </div>
    </div>
  )
}
