<script setup lang="ts">
import { onMounted, ref, nextTick, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, darkTheme } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import ConversationList from '../components/ConversationList.vue'
import ChatBubble from '../components/ChatBubble.vue'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const chat = useChatStore()

const inputText = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const isDark = ref(localStorage.getItem('yuanbot_theme') === 'dark')
const streamingText = ref('')
const isStreaming = ref(false)
const showAdminLink = computed(() => auth.isAdmin)

const theme = computed(() => (isDark.value ? darkTheme : undefined))

// 主题切换（持久化）
const toggleTheme = () => {
  isDark.value = !isDark.value
  localStorage.setItem('yuanbot_theme', isDark.value ? 'dark' : 'light')
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

const providers = ref<any[]>([])
const activeProvider = ref('')
const sidebarVisible = ref(window.innerWidth > 768)
const isMobile = ref(window.innerWidth <= 768)

// 响应式监听
window.addEventListener('resize', () => {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) sidebarVisible.value = true
})

// 加载 Provider 列表
async function loadProviders() {
  try {
    providers.value = await api.listProviders() as any[]
    const active = providers.value.find((p: any) => p.is_default)
    if (active) activeProvider.value = active.provider_id
  } catch {}
}

onMounted(async () => {
  const ok = await auth.checkAuth()
  if (!ok) {
    router.push('/login')
    return
  }
  await chat.loadConversations()
  loadProviders()
  // 检测系统主题偏好（已有 localStorage 值则不覆盖）
  if (!localStorage.getItem('yuanbot_theme')) {
    isDark.value = window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
})

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
    // 使用 WebSocket 流式发送
    if (chat.currentConvId) {
      isStreaming.value = true
      streamingText.value = ''

      // 添加用户消息到本地
      chat.addLocalMessage('user', text)

      api.connectWS(chat.currentConvId, {
        onStart: (_convId: string) => {
          streamingText.value = ''
        },
        onDelta: (delta: string) => {
          streamingText.value += delta
        },
        onEnd: (fullText: string, _convId: string) => {
          chat.addLocalMessage('assistant', fullText || streamingText.value)
          streamingText.value = ''
          isStreaming.value = false
          api.disconnectWS()
          chat.loadConversations()
        },
        onError: (_errMsg: string) => {
          // 回退到 REST API
          isStreaming.value = false
          api.disconnectWS()
          chat.sendMessageFallback(text)
        },
      })

      api.sendWSMessage(text, chat.currentConvId)
    } else {
      // 新会话使用 REST API
      await chat.sendMessage(text)
    }
  } catch (e: any) {
    message.error(e.message || '发送失败')
    isStreaming.value = false
  }
}

function handleNewConversation() {
  chat.createConversation()
  if (isMobile.value) sidebarVisible.value = false
}

function handleLogout() {
  api.logout()
  auth.logout()
  router.push('/login')
}

function handleCopyMessage(content: string) {
  navigator.clipboard.writeText(content)
  message.success('已复制')
}

function handleRegenerate(_messageId: string) {
  message.info('重新生成功能开发中')
}
</script>

<template>
  <n-config-provider :theme="theme">
    <n-layout has-sider style="height: 100vh">
      <!-- 左侧边栏 -->
      <n-layout-sider
        bordered
        :width="isMobile ? 280 : 260"
        :native-scrollbar="false"
        :show-trigger="false"
        :collapsed="!sidebarVisible"
        :collapsed-width="0"
        :position="'absolute'"
        :style="isMobile ? 'z-index: 1000; position: fixed; height: 100vh' : ''"
      >
        <div style="padding: 16px; display: flex; flex-direction: column; height: 100%">
          <div style="text-align: center; margin-bottom: 16px">
            <n-text strong style="font-size: 18px">🌸 缘·Bot</n-text>
          </div>

          <n-button type="primary" block @click="handleNewConversation" style="margin-bottom: 12px">
            + 新会话
          </n-button>

          <div style="flex: 1; overflow: auto">
            <ConversationList />
          </div>

          <n-divider />

          <!-- 记忆快捷入口 -->
          <n-space vertical :size="8" style="margin-bottom: 12px">
            <n-button text @click="router.push('/memory')">
              🧠 记忆浏览器
            </n-button>
            <n-button text @click="router.push('/providers')">
              🔌 Provider 管理
            </n-button>
            <n-button text @click="router.push('/plugins')">
              🧩 插件管理
            </n-button>
            <n-button text @click="router.push('/logs')">
              📋 实时日志
            </n-button>
            <n-button text @click="router.push('/config')" v-if="showAdminLink">
              ⚙️ 配置编辑
            </n-button>
            <n-button text @click="router.push('/admin')" v-if="showAdminLink">
              📊 管理面板
            </n-button>
          </n-space>

          <!-- 当前 Provider -->
          <div style="margin-bottom: 12px" v-if="providers.length > 0">
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 4px">当前 Provider</n-text>
            <n-select
              v-model:value="activeProvider"
              :options="providers.filter((p: any) => p.enabled).map((p: any) => ({ label: p.name || p.provider_id, value: p.provider_id }))"
              size="small"
              @update:value="(val: string) => { activeProvider = val; message.info('切换需重启服务生效') }"
            />
          </div>

          <!-- 用户信息 + 主题切换 -->
          <n-space justify="space-between" align="center">
            <n-text depth="3">{{ auth.user?.display_name }}</n-text>
            <n-space :size="4">
              <n-button text @click="toggleTheme">
                {{ isDark ? '☀️' : '🌙' }}
              </n-button>
              <n-button text @click="handleLogout">退出</n-button>
            </n-space>
          </n-space>
        </div>
      </n-layout-sider>

      <!-- 移动端遮罩层 -->
      <div
        v-if="isMobile && sidebarVisible"
        class="sidebar-overlay"
        @click="sidebarVisible = false"
      />

      <!-- 右侧聊天区 -->
      <n-layout-content style="display: flex; flex-direction: column; height: 100vh">
        <!-- 顶部栏 -->
        <n-layout-header bordered style="padding: 12px 20px; display: flex; align-items: center; gap: 8px">
          <n-button text @click="sidebarVisible = !sidebarVisible" style="font-size: 20px">
            {{ sidebarVisible && isMobile ? '✕' : '☰' }}
          </n-button>
          <n-text strong style="font-size: 16px; flex: 1">
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
          :style="{ flex: 1, padding: isMobile ? '12px' : '20px', overflowY: 'auto' }"
        >
          <n-empty
            v-if="!chat.currentConvId"
            description="选择或创建一个会话开始聊天"
            style="margin-top: 40%"
          />
          <n-spin
            v-else-if="chat.loadingMessages"
            size="large"
            style="margin-top: 40%; display: flex; justify-content: center"
          />
          <template v-else>
            <ChatBubble
              v-for="msg in chat.messages"
              :key="msg.message_id"
              :message="msg"
              @copy="handleCopyMessage"
              @regenerate="handleRegenerate"
            />
            <!-- 流式输出中 -->
            <div v-if="isStreaming" class="chat-bubble-row">
              <div class="bubble-avatar">🌸</div>
              <div class="bubble-content">
                <div class="bubble-text bubble-ai">{{ streamingText }}▌</div>
              </div>
            </div>
            <div v-if="chat.sending && !isStreaming" style="padding: 8px 0; color: var(--n-text-color-3)">
              <n-spin size="small" /> AI 思考中...
            </div>
          </template>
        </n-layout-content>

        <!-- 输入区域 -->
        <n-layout-footer bordered :style="{ padding: isMobile ? '8px 12px' : '12px 20px' }">
          <n-space :size="8" style="width: 100%">
            <n-input
              v-model:value="inputText"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="输入消息... (Enter 发送)"
              style="flex: 1"
              @keydown.enter.exact.prevent="handleSend"
            />
            <n-button type="primary" :loading="chat.sending || isStreaming" @click="handleSend">
              发送
            </n-button>
          </n-space>
        </n-layout-footer>
      </n-layout-content>
    </n-layout>
  </n-config-provider>
</template>

<style scoped>
/* 移动端适配 */
@media (max-width: 768px) {
  .bubble-content { max-width: 85%; }
  .bubble-text { padding: 8px 12px; font-size: 14px; }
  .bubble-avatar { width: 30px; height: 30px; font-size: 14px; }
  .chat-bubble-row { gap: 8px; margin-bottom: 12px; }
}

.chat-bubble-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.bubble-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: var(--n-border-color);
  flex-shrink: 0;
}
.bubble-content { max-width: 70%; }
.bubble-text {
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
.bubble-ai {
  background: var(--n-card-color);
  border: 1px solid var(--n-border-color);
  border-bottom-left-radius: 4px;
}

/* 移动端遮罩层 */
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .bubble-content { max-width: 85%; }
  .bubble-text { padding: 8px 12px; font-size: 14px; }
  .bubble-avatar { width: 30px; height: 30px; font-size: 14px; }
}
</style>
