export default function LookupPage() {
  return (
    <div className="page on">
      <h1 className="title">我来画 · 查库</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>画出正确结构</div>
        <div className="row">
          <div style={{ flex: 1, border: '1px dashed var(--line)', borderRadius: 8, height: 150, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)' }}>化学结构编辑器占位</div>
          <div style={{ flex: 1 }}>
            <div className="field"><label>导出的 SMILES</label><input defaultValue="CC(=O)Nc1ccc(cc1)S(=O)(=O)N" /></div>
            <div className="field" style={{ marginTop: 12 }}><label>来源</label><input readOnly value="Bayreuther1973 · DOI 10.1002/… · 1973" /></div>
            <div style={{ marginTop: 14 }}><button className="btn pri">查数据库</button></div>
          </div>
        </div>
      </div>
      <div className="row">
        <div className="card" style={{ flex: 1, borderColor: 'var(--green)' }}>
          <div title="识别对的都落在这里——库里一定有；画对的也可能落这里" style={{ fontSize: 16, fontWeight: 600, color: 'var(--green)', marginBottom: 10 }}>查到了</div>
          <p>数据库条目：CID-24801</p>
          <p>环数 1 · 环大小 6 · 标签 N O</p>
          <p>回流：匹配训练 + 拓扑训练</p>
        </div>
        <div className="card" style={{ flex: 1, borderColor: 'var(--red)' }}>
          <div title="库中无此结构——「查无」本身是发现信号，记录 DOI 与年份" style={{ fontSize: 16, fontWeight: 600, color: 'var(--red)', marginBottom: 10 }}>没查到 · 标记缺口</div>
          <p>库中无此结构 · 未入库</p>
          <p>DOI 10.1002/…</p>
          <p>年份 1973</p>
        </div>
      </div>
    </div>
  )
}
