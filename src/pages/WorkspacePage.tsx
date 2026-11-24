export default function WorkspacePage() {
  return (
    <div className="page on">
      <h1 className="title">工作区</h1>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>当前工作区</div>
        <div className="field">
          <label title="数据下载、存储的位置">工作区目录</label>
          <input readOnly value="F:\CSD-workspace" />
        </div>
      </div>
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>更换工作区</div>
        <div className="field" style={{ maxWidth: 360 }}>
          <label>授权另一个文件夹</label>
          <button className="btn" title="换文件夹后若没有原数据，需重新下载">选择文件夹…</button>
        </div>
      </div>
      <div className="devpanel">
        <b>工作区初始化这一步</b>
        <div className="steps">
          <div className="step"><b>输入</b><span>用户选的文件夹</span></div>
          <div className="step"><b>中间产物</b><span>API 授权句柄</span></div>
          <div className="step"><b>输出</b><span>数据落点目录</span></div>
        </div>
      </div>
    </div>
  )
}
