import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null }
  static getDerivedStateFromError(err: Error) { return { err } }
  render() {
    if (this.state.err) {
      return (
        <div style={{ padding: 24, fontFamily: 'monospace', color: '#c0392b' }}>
          <h2>页面出错了（这是一个 bug，不是你的操作问题）</h2>
          <p>{String(this.state.err)}</p>
          <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', color: '#555' }}>{this.state.err.stack}</pre>
          <button onClick={() => location.reload()}>重新加载</button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
