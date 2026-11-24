import { useState } from 'react'
import { BOOTSTRAP_FILES, type BootstrapFile } from './bootstrapFiles'
import { pickDirectory, saveDirHandle, writeAll, downloadFile } from './updater'

// 引导部署：后端离线时的首屏。用户全程只做三件事——
// ① 点按钮把启动文件写进本地工作区 ② 双击 BAT 起后端 ③ 等页面自动连上。

type PickState = 'idle' | 'writing' | 'done' | 'error' | 'unsupported'

function isWindows(): boolean { return /Windows/i.test(navigator.userAgent) }

async function writeBootstrapFiles(onProgress: (n: number) => void): Promise<void> {
  const dir = await pickDirectory()
  await writeAll(dir, onProgress)
  await saveDirHandle(dir)
}

const card: React.CSSProperties = {
  border: '1px solid var(--line)', borderRadius: 10, padding: '16px 20px',
  maxWidth: 560, textAlign: 'left',
}

export default function BootstrapGuide({ onRetry }: { onRetry: () => void }) {
  const [pick, setPick] = useState<PickState>('idle')
  const [written, setWritten] = useState(0)
  const [err, setErr] = useState('')

  async function onPick() {
    setPick('writing'); setErr('')
    try {
      await writeBootstrapFiles(setWritten)
      setPick('done')
    } catch (e) {
      if (e instanceof Error && e.message === 'unsupported') setPick('unsupported')
      else if (e instanceof DOMException && e.name === 'AbortError') setPick('idle')
      else { setPick('error'); setErr(String(e)) }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '40px 24px', minHeight: '100vh', boxSizing: 'border-box', overflowY: 'auto' }}>
      <header style={{ textAlign: 'center' }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>CSD · 首次使用</h1>
        <p style={{ margin: '8px 0 0', fontSize: 14, color: 'var(--muted)' }}>
          结构式识别在你自己的电脑上运行，文献不出本机。第一次使用，按下面三步准备。
        </p>
      </header>

      <section style={card}>
        <h2 style={{ fontSize: 15, margin: '0 0 8px' }}>第 1 步 · 把后端放进一个本地文件夹</h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 10px' }}>
          点按钮，选一个<strong>新建的空文件夹</strong>（比如「CSD」）。后端文件会自动写进去，之后你的文献和结果也都放在这里。
        </p>
        <p style={{ fontSize: 13, color: '#b45309', margin: '0 0 10px' }}>
          <strong>文件夹名字和路径必须用英文</strong>（例如 <code>C:\CSD</code>），不能用中文——Python 安装器不支持中文路径。
        </p>
        {pick !== 'unsupported' && (
          <button className="btn pri" onClick={() => void onPick()} disabled={pick === 'writing'}>
            {pick === 'writing' ? '写入中…' : pick === 'done' ? `已写入 ${written}/${BOOTSTRAP_FILES.length} 个文件（可重新写入）` : '选择文件夹并写入后端文件'}
          </button>
        )}
        {pick === 'error' && <p style={{ color: '#c0392b', fontSize: 13 }}>写入失败：{err}</p>}
        {pick === 'unsupported' && (
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            <p>当前浏览器不支持一键写入，请逐个下载下面 {BOOTSTRAP_FILES.length} 个文件，按显示的相对路径放进同一个文件夹：</p>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, maxHeight: 200, overflowY: 'auto' }}>
              {BOOTSTRAP_FILES.map((f: BootstrapFile) => (
                <li key={f.path} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span>{f.path}</span><button className="btn" onClick={() => downloadFile(f)}>下载</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section style={card}>
        <h2 style={{ fontSize: 15, margin: '0 0 8px' }}>第 2 步 · 运行启动器</h2>
        {isWindows() ? (
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
            打开刚选的文件夹，<strong>双击 start-windows.bat</strong>。首次会自动准备运行环境并下载分子识别模型（约 50MB），保持黑窗口开启。
          </p>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
            在文件夹里打开终端，运行 <code>bash start-windows.bat</code>。首次会自动准备环境，保持窗口开启。
          </p>
        )}
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '8px 0 0' }}>
          启动器不写系统目录、不改注册表，所有东西都在这个文件夹里；要卸载就删掉这个文件夹。
        </p>
      </section>

      <section style={card}>
        <h2 style={{ fontSize: 15, margin: '0 0 8px' }}>第 3 步 · 等窗口显示监听地址，然后回到这里</h2>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 10px' }}>
          启动窗口出现 <code>http://127.0.0.1:8765</code> 后，本页会在几秒内自动连上；也可以立刻点下面按钮。
        </p>
        <button className="btn pri" onClick={onRetry}>重新连接</button>
      </section>
    </div>
  )
}
