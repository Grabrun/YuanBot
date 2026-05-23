/**
 * YuanBot WebUI API 客户端
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

class ApiClient {
  private token: string | null = null

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

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
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

  async getMetrics(): Promise<Record<string, any>> {
    return this.request<Record<string, any>>('/api/admin/metrics')
  }

  async refreshToken(): Promise<{ token: string }> {
    const data = await this.request<{ token: string }>('/api/auth/refresh', {
      method: 'POST',
    })
    this.setToken(data.token)
    return data
  }

  logout() {
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

  async sendMessage(
    content: string,
    conversationId?: string
  ): Promise<{
    conversation_id: string
    user_message: { message_id: string; content: string }
    ai_message: { message_id: string; content: string }
  }> {
    const body: Record<string, string> = { content }
    if (conversationId) body.conversation_id = conversationId
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  // ── Provider ────────────────────────────

  async listProviders(): Promise<Record<string, unknown>[]> {
    const data = await this.request<{ providers: Record<string, unknown>[] }>('/api/providers')
    return data.providers
  }
}

export const api = new ApiClient()
