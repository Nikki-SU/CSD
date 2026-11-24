// 引导部署 / 本地后端更新。
// 浏览器只写 BOOTSTRAP_FILES 列出的固定路径，不碰用户 data/、.runtime/ 或其它文件。
// start-windows.bat 是不可变入口（已存在不覆盖）；run-windows.bat 写 .new 下次启动换入。

import { BOOTSTRAP_FILES, BUNDLE_VERSION, type BootstrapFile } from './bootstrapFiles'

const DB_NAME = 'csd'
const STORE = 'handles'
const DIR_KEY = 'bootstrap'
const APPLIED_KEY = 'csd_bundle_applied_v1'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function saveDirHandle(dir: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(dir, DIR_KEY)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } finally { db.close() }
}

export async function loadDirHandle(): Promise<FileSystemDirectoryHandle | null> {
  try {
    const db = await openDb()
    const value = await new Promise<FileSystemDirectoryHandle | null>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(DIR_KEY)
      req.onsuccess = () => resolve((req.result as FileSystemDirectoryHandle) ?? null)
      req.onerror = () => reject(req.error)
    })
    db.close()
    return value
  } catch { return null }
}

export function pickDirectory(): Promise<FileSystemDirectoryHandle> {
  const picker = window.showDirectoryPicker
  if (!picker) return Promise.reject(new Error('unsupported'))
  return picker({ id: 'csd', mode: 'readwrite' })
}

export async function ensureWritePermission(dir: FileSystemDirectoryHandle): Promise<boolean> {
  const h = dir as FileSystemDirectoryHandle & {
    queryPermission?: (d: { mode: 'readwrite' }) => Promise<PermissionState>
    requestPermission?: (d: { mode: 'readwrite' }) => Promise<PermissionState>
  }
  const d = { mode: 'readwrite' as const }
  try {
    if (h.queryPermission && (await h.queryPermission(d)) === 'granted') return true
    if (h.requestPermission && (await h.requestPermission(d)) === 'granted') return true
    return false
  } catch { return false }
}

async function resolveDir(root: FileSystemDirectoryHandle, path: string, create: boolean) {
  const parts = path.split('/')
  let dir = root
  for (let i = 0; i < parts.length - 1; i++) dir = await dir.getDirectoryHandle(parts[i], { create })
  return { dir, name: parts[parts.length - 1] }
}

async function readOne(root: FileSystemDirectoryHandle, path: string): Promise<string | null> {
  try {
    const { dir, name } = await resolveDir(root, path, false)
    const fh = await dir.getFileHandle(name)
    return await (await fh.getFile()).text()
  } catch { return null }
}

async function writeOne(root: FileSystemDirectoryHandle, f: BootstrapFile): Promise<void> {
  const { dir, name } = await resolveDir(root, f.path, true)
  const fh = await dir.getFileHandle(name, { create: true })
  const w = await fh.createWritable()
  await w.write(f.content)
  await w.close()
}

/** 引导首次写入：全部无条件覆盖。launcher 也写（首次本来就没有）。 */
export async function writeAll(root: FileSystemDirectoryHandle, onProgress?: (n: number) => void): Promise<void> {
  let n = 0
  for (const f of BOOTSTRAP_FILES) { await writeOne(root, f); n++; onProgress?.(n) }
}

export type UpdateResult = { changed: number; launcherStale: string[] }

/** 增量更新：只写有差异的文件；launcher 只登记不覆盖；promote 写 .new 待换入。 */
export async function applyUpdate(root: FileSystemDirectoryHandle, onProgress?: (n: number) => void): Promise<UpdateResult> {
  let changed = 0
  const launcherStale: string[] = []
  for (const f of BOOTSTRAP_FILES) {
    if (f.promote) {
      const current = await readOne(root, f.path)
      const pending = await readOne(root, `${f.path}.new`)
      if (current === f.content && pending === null) continue
      await writeOne(root, { ...f, path: `${f.path}.new` })
      changed++; onProgress?.(changed)
      continue
    }
    if ((await readOne(root, f.path)) === f.content) continue
    if (f.launcher) { launcherStale.push(f.path); continue }
    await writeOne(root, f)
    changed++; onProgress?.(changed)
  }
  return { changed, launcherStale }
}

/** 页面内置版本比本地后端新 → 需要更新本地文件。 */
export function isOutdated(local: { frontend: number }): boolean {
  return (local?.frontend ?? 0) < BUNDLE_VERSION.frontend
}

/** 后端代码落后 → 写入后需要重启进程。 */
export function backendOutdated(local: { backend: number }): boolean {
  return (local?.backend ?? 0) < BUNDLE_VERSION.backend
}

export function markBundleApplied(): void {
  try { localStorage.setItem(APPLIED_KEY, String(BUNDLE_VERSION.frontend)) } catch { /* 隐私模式忽略 */ }
}

export function bundleApplied(): boolean {
  try { return Number(localStorage.getItem(APPLIED_KEY) || 0) >= BUNDLE_VERSION.frontend } catch { return false }
}

/** 不支持 File System Access 时，逐个下载。 */
export function downloadFile(f: BootstrapFile): void {
  const blob = new Blob([f.content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = f.path.split('/').pop() || f.path
  a.click()
  URL.revokeObjectURL(url)
}
