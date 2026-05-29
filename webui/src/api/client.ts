/**
 * YuanBot WebUI API 客户端
 * 设计文档第7节完整实现
 */

const API_BASE = import.meta.env.VITE_API_BASE || ''

export interface User {
  user_id: string
  username: string
  display_name: string
  role: string
  has_api_key: boolean
}

export interface Conversation {
  conversation_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface Message {
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

export interface LoginResponse {
  token: string
  user: User
  expires_in: number
}

export interface StreamCallbacks {
  onStart?: (conversationId: string) => void
  onDelta?: (delta: string) => void
  onEnd?: (fullText: string, conversationId: string) => void
  onError?: (message: string) => void
}

class ApiClient {
  private token: string | null = null
  private ws: WebSocket | null = null
  private wsCallbacks: StreamCallbacks | null = null
  private currentConvId: string | null = null

  setToken(token: string) {
    this.token = token
    localStorage.setItem('yuanbot_token', token)
  }

  getToken(): string | null {
    if (!this.token) {
      this.token = localStorage.getItem('yuanbot_token')
    }
    return this.token
  }

  clearToken() {
    this.token = null
    localStorage.removeItem('yuanbot_token')
  }

  private headers(): HeadersInit {
    const h: HeadersInit = { 'Content-Type': 'application/json' }
    const token = this.getToken()
    if (token) h['Authorization'] = `Bearer ${token}`
    return h
  }

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const resp = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...this.headers(), ...options.headers },
    })
    if (resp.status === 401) {
      this.clearToken()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || 'Request failed')
    }
    return resp.json()
  }

  // ── 认证 ────────────────────────────────

  async login(username: string, password: string): Promise<LoginResponse> {
    const data = await this.request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    this.setToken(data.token)
    return data
  }

  async loginWithApiKey(apiKey: string): Promise<LoginResponse> {
    const data = await this.request<LoginResponse>('/api/auth/api-key', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    })
    this.setToken(data.token)
    return data
  }

  async getMe(): Promise<User> {
    return this.request<User>('/api/auth/me')
  }

  async refreshToken(): Promise<{ token: string }> {
    const data = await this.request<{ token: string }>('/api/auth/refresh', { method: 'POST' })
    this.setToken(data.token)
    return data
  }

  logout() {
    this.disconnectWS()
    this.clearToken()
    fetch('/api/auth/logout', { method: 'POST', headers: this.headers() }).catch(() => {})
  }

  // ── 会话 ────────────────────────────────

  async listConversations(): Promise<Conversation[]> {
    const data = await this.request<{ conversations: Conversation[] }>('/api/conversations')
    return data.conversations
  }

  async createConversation(title = '新会话'): Promise<Conversation> {
    return this.request<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    })
  }

  async deleteConversation(id: string): Promise<void> {
    await this.request(`/api/conversations/${id}`, { method: 'DELETE' })
  }

  async getMessages(convId: string, limit = 50): Promise<Message[]> {
    const data = await this.request<{ messages: Message[] }>(
      `/api/conversations/${convId}/messages?limit=${limit}`
    )
    return data.messages
  }

  async sendMessage(content: string, conversationId?: string) {
    const body: Record<string, string> = { content }
    if (conversationId) body.conversation_id = conversationId
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  // ── Provider ────────────────────────────

  async listProviders() {
    const data = await this.request<{ providers: Record<string, unknown>[] }>('/api/providers')
    return data.providers
  }

  // ── 管理 ────────────────────────────────

  async getMetrics() {
    return this.request<Record<string, unknown>>('/api/admin/metrics')
  }

  async listUsers() {
    return this.request<{ users: User[] }>('/api/admin/users')
  }

  async createUser(username: string, password: string, displayName = '', role = 'user') {
    return this.request('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name: displayName, role }),
    })
  }

  async deleteUser(userId: string) {
    return this.request(`/api/admin/users/${userId}`, { method: 'DELETE' })
  }

  async generateApiKey(userId: string) {
    return this.request<{ api_key: string }>(`/api/admin/users/${userId}/api-key`, {
      method: 'POST',
    })
  }

  async revokeApiKey(userId: string) {
    return this.request(`/api/admin/users/${userId}/api-key`, { method: 'DELETE' })
  }

  async triggerBackup() {
    return this.request('/api/admin/backup', { method: 'POST' })
  }

  async listBackups() {
    return this.request<{ backups: Record<string, unknown>[] }>('/api/admin/backups')
  }

  // ── WebSocket 流式聊天 ──────────────────

  connectWS(convId: string, callbacks: StreamCallbacks) {
    this.disconnectWS()
    this.currentConvId = convId
    this.wsCallbacks = callbacks

    const token = this.getToken()
    const wsBase = API_BASE.replace(/^http/, 'ws') || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
    const url = `${wsBase}/ws/chat?token=${token}`

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      // 订阅会话
      this.ws?.send(JSON.stringify({ type: 'subscribe', conversation_id: convId }))
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'stream_start':
            this.wsCallbacks?.onStart?.(data.conversation_id)
            break
          case 'stream_delta':
            this.wsCallbacks?.onDelta?.(data.delta || '')
            break
          case 'stream_end':
            this.wsCallbacks?.onEnd?.(data.full_text || '', data.conversation_id)
            break
          case 'error':
            this.wsCallbacks?.onError?.(data.message)
            break
          case 'pong':
            break
        }
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }

    this.ws.onerror = () => {
      this.wsCallbacks?.onError?.('WebSocket 连接错误')
    }

    this.ws.onclose = () => {
      this.ws = null
    }
  }

  sendWSMessage(text: string, convId?: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.wsCallbacks?.onError?.('WebSocket 未连接')
      return
    }
    this.ws.send(JSON.stringify({
      type: 'message',
      text,
      conversation_id: convId || this.currentConvId,
    }))
  }

  disconnectWS() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.wsCallbacks = null
    this.currentConvId = null
  }
}

export const api = new ApiClient()
