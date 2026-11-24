// 轻量页面跳转：App 挂载时注册，子页面直接调用，避免层层传 prop。
type PageId = 'work' | 'new' | 'review' | 'report' | 'screen' | 'style' | 'topo' | 'diag' | 'lookup' | 'settings'
let goFn: ((id: PageId) => void) | null = null

export function registerNav(fn: (id: PageId) => void): void {
  goFn = fn
}

export function navigate(id: PageId): void {
  goFn?.(id)
}
