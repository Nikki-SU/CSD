import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    // public/jsme 有 160+ 个 GWT 分片文件，每次清空会触发环境的安全删除保护；
    // 这些文件内容不变（JSME 是固定版本），保留不清空是安全的。
    emptyOutDir: false,
  },
})
