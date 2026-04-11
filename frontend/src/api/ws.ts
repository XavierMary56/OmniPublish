/** OmniPublish — WebSocket 封装 */

type WsHandler = (data: any) => void

export class OmniWs {
  private ws: WebSocket | null = null
  private handlers: Map<string, WsHandler[]> = new Map()
  private url: string
  private reconnectTimer: number | null = null

  constructor(url: string) {
    this.url = url
  }

  connect() {
    if (this.ws && this.ws.readyState <= 1) return
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.ws = new WebSocket(`${protocol}//${location.host}${this.url}`)
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
      this.reconnectTimer = window.setTimeout(() => this.connect(), 3000)
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
