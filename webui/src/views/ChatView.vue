<script setup lang="ts">
import { onMounted, ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import ConversationList from '../components/ConversationList.vue'
import ChatBubble from '../components/ChatBubble.vue'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const chat = useChatStore()

const inputText = ref('')
const chatContainer = ref<HTMLElement | null>(null)

onMounted(async () => {
  const ok = await auth.checkAuth()
  if (!ok) {
    router.push('/login')
    return
  }
  await chat.loadConversations()
})

// 自动滚动到底部
watch(
  () => chat.messages.length,
  async () => {
    await nextTick()
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  }
)

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chat.sending) return
  inputText.value = ''

  try {
    await chat.sendMessage(text)
  } catch (e: any) {
    message.error(e.message || '发送失败')
  }
}

function handleNewConversation() {
  chat.createConversation()
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <n-layout has-sider style="height: 100vh">
    <!-- 左侧边栏 -->
    <n-layout-sider
      bordered
      :width="260"
      :native-scrollbar="false"
      style="background: var(--n-color)"
    >
      <div style="padding: 16px; display: flex; flex-direction: column; height: 100%">
        <!-- 标题 -->
        <div style="text-align: center; margin-bottom: 16px">
          <n-text strong style="font-size: 18px">🌸 缘·Bot</n-text>
        </div>

        <!-- 新建按钮 -->
        <n-button type="primary" block @click="handleNewConversation" style="margin-bottom: 12px">
          + 新会话
        </n-button>

        <!-- 会话列表 -->
        <div style="flex: 1; overflow: auto">
          <ConversationList />
        </div>

        <!-- 用户信息 -->
        <n-divider />
        <n-space justify="space-between" align="center">
          <n-text depth="3">{{ auth.user?.display_name }}</n-text>
          <n-button text @click="handleLogout">退出</n-button>
        </n-space>
      </div>
    </n-layout-sider>

    <!-- 右侧聊天区 -->
    <n-layout-content style="display: flex; flex-direction: column; height: 100vh">
      <!-- 顶部栏 -->
      <n-layout-header bordered style="padding: 12px 20px; display: flex; align-items: center">
        <n-text strong style="font-size: 16px">
          {{ chat.currentConversation?.title || '选择或创建会话' }}
        </n-text>
        <div style="flex: 1" />
        <n-text depth="3" v-if="chat.currentConversation">
          {{ chat.currentConversation.message_count }} 条消息
        </n-text>
      </n-layout-header>

      <!-- 消息区域 -->
      <n-layout-content
        ref="chatContainer"
        :native-scrollbar="false"
        style="flex: 1; padding: 20px; overflow-y: auto"
      >
        <n-empty v-if="!chat.currentConvId" description="选择或创建一个会话开始聊天" style="margin-top: 40%" />
        <n-spin v-else-if="chat.loadingMessages" size="large" style="margin-top: 40%; display: flex; justify-content: center" />
        <template v-else>
          <ChatBubble
            v-for="msg in chat.messages"
            :key="msg.message_id"
            :message="msg"
          />
          <div v-if="chat.sending" style="padding: 8px 0; color: var(--n-text-color-3)">
            <n-spin size="small" /> AI 思考中...
          </div>
        </template>
      </n-layout-content>

      <!-- 输入区域 -->
      <n-layout-footer bordered style="padding: 12px 20px">
        <n-space :size="8">
          <n-input
            v-model:value="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            style="flex: 1"
            @keydown.enter.exact.prevent="handleSend"
          />
          <n-button type="primary" :loading="chat.sending" @click="handleSend">
            发送
          </n-button>
        </n-space>
      </n-layout-footer>
    </n-layout-content>
  </n-layout>
</template>
