export default function SettingsPage() {
  return (
    <div className="page on">
      <h1 className="title">设置</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 12 }}>后端连接</div>
        <div className="field"><label>本地后端地址</label><input defaultValue="http://127.0.0.1:8765" /></div>
      </div>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 12 }}>取代基规则</div>
        <div className="field"><label>图上写法 → 代表结构 → 指标贡献</label><input defaultValue="Me → CH3 → +1 碳" /></div>
      </div>
    </div>
  )
}
