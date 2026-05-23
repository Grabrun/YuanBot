<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../api/client'

const props = defineProps<{
  message: Message
}>()

const emit = defineEmits<{
  copy: [content: string]
  regenerate: [messageId: string]
}>()

const isUser = computed(() => props.message.role === 'user')
const timeStr = computed(() => {
  const d = new Date(props.message.timestamp)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})

function handleCopy() {
  navigator.clipboard?.writeText(props.message.content)
  emit('copy', props.message.content)
}

function handleRegenerate() {
  emit('regenerate', props.message.message_id)
}
</script>

<template>
  <div class="chat-bubble-row" :class="{ 'is-user': isUser }">
    <div class="bubble-avatar">
      {{ isUser ? '👤' : '🌸' }}
    </div>
    <div class="bubble-content">
      <div class="bubble-meta">
        <span class="bubble-name">{{ isUser ? '你' : '小缘' }}</span>
        <span class="bubble-time">{{ timeStr }}</span>
      </div>
      <div class="bubble-text" :class="{ 'bubble-user': isUser, 'bubble-ai': !isUser }">
        {{ message.content }}
      </div>
      <div class="bubble-actions">
        <n-button text size="tiny" @click="handleCopy">复制</n-button>
        <n-button v-if="!isUser" text size="tiny" @click="handleRegenerate">重新生成</n-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-bubble-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.chat-bubble-row.is-user {
  flex-direction: row-reverse;
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
.bubble-meta {
  font-size: 12px;
  color: var(--n-text-color-3);
  margin-bottom: 4px;
}
.is-user .bubble-meta { text-align: right; }
.bubble-name {
  font-weight: 500;
  margin-right: 8px;
}
.bubble-text {
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
.bubble-user {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
}
.bubble-ai {
  background: var(--n-card-color);
  border: 1px solid var(--n-border-color);
  border-bottom-left-radius: 4px;
}
.bubble-actions {
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}
.chat-bubble-row:hover .bubble-actions {
  opacity: 1;
}
</style>
