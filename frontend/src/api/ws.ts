/** OmniPublish — WebSocket 封装 */

type WsHandler = (data: any) => void

export class OmniWs {
  private ws: WebSocket | null = null
  private handlers: Map<string, WsHandler[]> = new Map()
  private url: string
  private reconnectTimer: number | null = null
  private reconnectAttempts = 0
  private maxReconnectDelay = 30000 // 最大 30 秒

  constructor(url: string) {
    this.url = url
  }

  connect(token?: string) {
    if (this.ws && this.ws.readyState <= 1) return
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    // 附加 token 到 URL query 参数进行认证
    const sep = this.url.includes('?') ? '&' : '?'
    const authUrl = token ? `${this.url}${sep}token=${encodeURIComponent(token)}` : this.url
    this.ws = new WebSocket(`${protocol}//${location.host}${authUrl}`)
    this.ws.onopen = () => {
      this.reconnectAttempts = 0 // 连接成功，重置退避计数
    }
    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        const type = data.type || 'message'
        const fns = this.handlers.get(type) || []
        fns.forEach((fn) => fn(data))
        // 通配符
        const all = this.handlers.get('*') || []
        all.forEach((fn) => fn(data))
      } catch {}
    }
    this.ws.onclose = () => {
      // 指数退避重连: 3s, 6s, 12s, 24s, 30s(cap)
      this.reconnectAttempts++
      const delay = Math.min(3000 * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay)
      this.reconnectTimer = window.setTimeout(() => this.connect(token), delay)
    }
    this.ws.onerror = () => this.ws?.close()
  }

  on(type: string, handler: WsHandler) {
    const list = this.handlers.get(type) || []
    list.push(handler)
    this.handlers.set(type, list)
  }

  off(type: string, handler?: WsHandler) {
    if (!handler) { this.handlers.delete(type); return }
    const list = (this.handlers.get(type) || []).filter((h) => h !== handler)
    this.handlers.set(type, list)
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectAttempts = 0
    this.ws?.close()
    this.ws = null
    this.handlers.clear()
  }
}

/** 创建任务级 WebSocket */
export function createTaskWs(taskId: number) {
  return new OmniWs(`/ws/pipeline/${taskId}`)
}

/** 全局通知 WebSocket */
export const notificationWs = new OmniWs('/ws/notifications')
