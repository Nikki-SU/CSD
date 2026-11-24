// 把后端源码 + bootstrap 启动文件嵌入前端（生成 src/bootstrapFiles.ts）。
// 引导部署用：GitHub Pages 页面把这些文件一键写入用户选定的本地文件夹。
// 由 package.json 的 prebuild 自动执行；后端 / bootstrap 改动后重新 build 即同步。
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoDir = frontendDir

// .bat 必须 CRLF + 纯 ASCII（cmd 按字节读，UTF-8 中文会错位执行）。
function normalize(name, text) {
  const lf = text.replace(/\r\n/g, '\n')
  if (name.endsWith('.bat')) {
    const nonAscii = [...lf].filter((ch) => ch.charCodeAt(0) > 0x7f)
    if (nonAscii.length > 0) {
      throw new Error(`${name} 含非 ASCII 字符（${nonAscii.slice(0, 5).join(' ')}）。Windows 批处理只能英文。`)
    }
    return lf.replace(/\n/g, '\r\n')
  }
  return lf
}

const files = []
function addDir(dirRel, prefix, filter) {
  const full = join(repoDir, dirRel)
  for (const name of readdirSync(full).sort()) {
    if (!filter(name)) continue
    files.push({
      path: `${prefix}${name}`,
      content: normalize(name, readFileSync(join(full, name), 'utf8')),
    })
  }
}

// 后端三层：server/worker + pipeline + training（worker 依赖 training.detect）
addDir('backend', 'backend/', (n) => n.endsWith('.py'))
addDir('pipeline', 'pipeline/', (n) => n.endsWith('.py'))
addDir('training', 'training/', (n) => n.endsWith('.py'))
// requirements
files.push({
  path: 'requirements.txt',
  content: normalize('requirements.txt', readFileSync(join(repoDir, 'requirements.txt'), 'utf8')),
})

// 启动器：start-windows.bat 是不可变入口，run-windows.bat 是可更新主体（写 .new 下次启动换入）
const LAUNCHER_ENTRIES = new Set(['start-windows.bat'])
const LAUNCHER_UPDATABLE = new Set(['run-windows.bat'])
for (const name of readdirSync(join(repoDir, 'bootstrap')).sort()) {
  if (name === '__pycache__') continue
  if (!/\.(bat|py)$/.test(name)) continue
  files.push({
    path: name,
    launcher: LAUNCHER_ENTRIES.has(name),
    promote: LAUNCHER_UPDATABLE.has(name),
    content: normalize(name, readFileSync(join(repoDir, 'bootstrap', name), 'utf8')),
  })
}

// 四段版本号从 backend/server.py 读
const src = readFileSync(join(repoDir, 'backend', 'server.py'), 'utf8')
const vm = src.match(/VERSION\s*=\s*\{\s*"frontend":\s*(\d+),\s*"backend":\s*(\d+),\s*"model":\s*(\d+),\s*"data":\s*(\d+)/)
if (!vm) throw new Error('backend/server.py 里找不到 VERSION 四段版本号')
const bundleVersion = { frontend: +vm[1], backend: +vm[2], model: +vm[3], data: +vm[4] }

const esc = (s) => JSON.stringify(s)
const body = files.map((f) => `  {
    path: ${esc(f.path)},
    content: ${esc(f.content)},${f.launcher ? '\n    launcher: true,' : ''}${f.promote ? '\n    promote: true,' : ''}
  }`).join(',\n')

const ts = `// 自动生成（scripts/embed-backend.mjs），勿手改；后端 / bootstrap 变更后重新 build。
export interface BootstrapFile {
  path: string
  content: string
  launcher?: boolean
  promote?: boolean
}

export const BUNDLE_VERSION = ${JSON.stringify(bundleVersion)}

export const BOOTSTRAP_FILES: BootstrapFile[] = [
${body}
]
`
writeFileSync(join(repoDir, 'src', 'bootstrapFiles.ts'), ts, 'utf8')

// 前端更新探测用：部署时把版本号写进 public/version.json，页面 no-store 拉取比对，
// 线上比页面编译时新就提示刷新（与后端版本无关）。
const publicDir = join(repoDir, 'public')
mkdirSync(publicDir, { recursive: true })
writeFileSync(join(publicDir, 'version.json'), JSON.stringify(bundleVersion), 'utf8')
console.log(`嵌入 ${files.length} 个文件到 src/bootstrapFiles.ts，版本 ${JSON.stringify(bundleVersion)}`)
