import { useEffect, useRef, useState } from 'react'

// JSME 化学结构编辑器封装。初始可传入 SMILES —— 这正是「都不对」后
// 预置候选 A 的结构、让用户只改不画的关键（从零画整分子画不过来）。
// JSME 由 jsme.nocache.js 异步加载，加载完回调 window.jsmeOnLoad。

type JSApplet = { JSME: new (el: string, w: string, h: string, opts?: Record<string, unknown>) => JsmeInstance }
type JsmeInstance = {
  getSmiles: () => string
  readGenericMolecularInput?: (s: string) => void
  setMolecule?: (s: string) => void
}

declare global {
  interface Window {
    JSApplet?: JSApplet
    jsmeOnLoad?: () => void
  }
}

let scriptLoading: Promise<void> | null = null

function loadJsme(): Promise<void> {
  if (window.JSApplet) return Promise.resolve()
  if (scriptLoading) return scriptLoading
  scriptLoading = new Promise<void>((resolve, reject) => {
    window.jsmeOnLoad = () => resolve()
    const s = document.createElement('script')
    s.src = `${import.meta.env.BASE_URL}jsme/jsme.nocache.js`
    s.onerror = () => reject(new Error('JSME 加载失败'))
    document.head.appendChild(s)
  })
  return scriptLoading
}

export default function MolEditor({
  initialSmiles = '',
  height = 260,
  onChange,
}: {
  initialSmiles?: string
  height?: number
  onChange?: (smiles: string) => void
}) {
  const holderRef = useRef<HTMLDivElement>(null)
  const appletRef = useRef<JsmeInstance | null>(null)
  const idRef = useRef(`jsme_${Math.random().toString(36).slice(2, 9)}`)
  const [ready, setReady] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    loadJsme().then(() => {
      if (!alive || !window.JSApplet) return
      const el = holderRef.current
      if (!el) return
      el.id = idRef.current
      const opts: Record<string, unknown> = { options: 'oldlook,star' }
      if (initialSmiles) opts.smiles = initialSmiles  // ← 预置结构，不从零画
      appletRef.current = new window.JSApplet.JSME(idRef.current, '100%', `${height}px`, opts)
      setReady(true)
    }).catch((e) => alive && setErr(String(e instanceof Error ? e.message : e)))
    return () => { alive = false }
    // initialSmiles 只在首次挂载时用于预置；后续变化由外部重建组件
  }, [height, initialSmiles])

  const emit = () => {
    const s = appletRef.current?.getSmiles?.() || ''
    onChange?.(s)
  }

  return (
    <div>
      <div ref={holderRef} style={{ border: '1px solid var(--line)', borderRadius: 8, minHeight: height, overflow: 'hidden' }} />
      <div className="row" style={{ gap: 8, marginTop: 8 }}>
        <button className="btn" onClick={emit} disabled={!ready}>取当前 SMILES</button>
        <button className="btn" onClick={() => { if (initialSmiles) appletRef.current?.setMolecule?.(initialSmiles) }} disabled={!ready}>
          复位为候选 A
        </button>
      </div>
      {err && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 6 }}>{err}</div>}
    </div>
  )
}
