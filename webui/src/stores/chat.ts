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

  async function sendMessage(content: string) {
    sending.value = true
    try {
      // 添加用户消息到本地
      const userMsg: Message = {
        message_id: `temp_${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      }
      messages.value.push(userMsg)

      // 发送到后端
      const result = await api.sendMessage(content, currentConvId.value || undefined)

      // 更新会话 ID（新会话时）
      if (!currentConvId.value) {
        currentConvId.value = result.conversation_id
        await loadConversations()
      }

      // 更新消息 ID
      const idx = messages.value.findIndex((m) => m.message_id === userMsg.message_id)
      if (idx >= 0) {
        messages.value[idx].message_id = result.user_message.message_id
      }

      // 添加 AI 回复
      messages.value.push({
        message_id: result.ai_message.message_id,
        role: 'assistant',
        content: result.ai_message.content,
        timestamp: new Date().toISOString(),
      })

      // 刷新会话列表（标题可能已更新）
      await loadConversations()
    } catch (e) {
      // 移除临时消息
      messages.value = messages.value.filter((m) => !m.message_id.startsWith('temp_'))
      throw e
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
    sendMessage,
  }
})
