import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, type Conversation, type Message } from '../api/client'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const currentConvId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const sending = ref(false)
  const loadingMessages = ref(false)

  const currentConversation = computed(() =>
    conversations.value.find((c) => c.conversation_id === currentConvId.value)
  )

  async function loadConversations() {
    conversations.value = await api.listConversations()
    if (!currentConvId.value && conversations.value.length > 0) {
      await selectConversation(conversations.value[0].conversation_id)
    }
  }

  async function selectConversation(convId: string) {
    currentConvId.value = convId
    loadingMessages.value = true
    try {
      messages.value = await api.getMessages(convId)
    } finally {
      loadingMessages.value = false
    }
  }

  async function createConversation(title = '新会话') {
    const conv = await api.createConversation(title)
    await loadConversations()
    await selectConversation(conv.conversation_id)
    return conv
  }

  async function deleteConversation(convId: string) {
    await api.deleteConversation(convId)
    if (currentConvId.value === convId) {
      currentConvId.value = null
      messages.value = []
    }
    await loadConversations()
  }

  function addLocalMessage(role: 'user' | 'assistant', content: string) {
    messages.value.push({
      message_id: `local_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      role,
      content,
      timestamp: new Date().toISOString(),
    })
  }

  async function sendMessage(content: string) {
    sending.value = true
    try {
      addLocalMessage('user', content)
      const result = await api.sendMessage(content, currentConvId.value || undefined)

      // 更新用户消息 ID
      const userIdx = messages.value.findIndex(
        (m) => m.role === 'user' && m.content === content && m.message_id.startsWith('local_')
      )
      if (userIdx >= 0) {
        messages.value[userIdx].message_id = result.user_message.message_id
      }

      addLocalMessage('assistant', result.ai_message.content)

      if (!currentConvId.value) {
        currentConvId.value = result.conversation_id
        await loadConversations()
      } else {
        await loadConversations()
      }
    } catch (e) {
      // 移除临时用户消息
      const idx = messages.value.findIndex(
        (m) => m.role === 'user' && m.content === content && m.message_id.startsWith('local_')
      )
      if (idx >= 0) messages.value.splice(idx, 1)
      throw e
    } finally {
      sending.value = false
    }
  }

  async function sendMessageFallback(content: string) {
    // WebSocket 失败时回退到 REST
    sending.value = true
    try {
      const result = await api.sendMessage(content, currentConvId.value || undefined)
      // 替换流式消息为最终结果
      const lastAiIdx = messages.value.length - 1
      if (lastAiIdx >= 0 && messages.value[lastAiIdx].role === 'assistant') {
        messages.value[lastAiIdx].content = result.ai_message.content
        messages.value[lastAiIdx].message_id = result.ai_message.message_id
      } else {
        addLocalMessage('assistant', result.ai_message.content)
      }
      await loadConversations()
    } catch (e: any) {
      addLocalMessage('assistant', `⚠️ 发送失败: ${e.message}`)
    } finally {
      sending.value = false
    }
  }

  return {
    conversations,
    currentConvId,
    currentConversation,
    messages,
    sending,
    loadingMessages,
    loadConversations,
    selectConversation,
    createConversation,
    deleteConversation,
    addLocalMessage,
    sendMessage,
    sendMessageFallback,
  }
})
