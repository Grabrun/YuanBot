<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import type { Message } from '../api/client'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
})

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
const renderedHtml = computed(() => {
  if (isUser.value) return ''
  return md.render(props.message.content)
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
      <!-- 用户消息：纯文本 -->
      <div v-if="isUser" class="bubble-text bubble-user">
        {{ message.content }}
      </div>
      <!-- AI 消息：Markdown 渲染 -->
      <div v-else class="bubble-text bubble-ai markdown-body" v-html="renderedHtml" />
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
/* Markdown 渲染样式 */
.markdown-body :deep(p) {
  margin: 0.4em 0;
}
.markdown-body :deep(code) {
  background: rgba(102, 126, 234, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'Courier New', monospace;
}
.markdown-body :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
  position: relative;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-size: 0.85em;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #667eea;
  padding-left: 12px;
  margin: 8px 0;
  color: var(--n-text-color-3);
}
.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: 12px 0 4px;
  font-weight: 600;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid var(--n-border-color);
  padding: 6px 10px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--n-card-color);
  font-weight: 600;
}
.markdown-body :deep(a) {
  color: #667eea;
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--n-border-color);
  margin: 12px 0;
}
.bubble-actions {
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}
.chat-bubble-row:hover .bubble-actions {
  opacity: 1;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .bubble-content { max-width: 85%; }
  .bubble-text { padding: 8px 12px; font-size: 14px; }
  .bubble-avatar { width: 30px; height: 30px; font-size: 14px; }
  .chat-bubble-row { gap: 8px; margin-bottom: 12px; }
}
</style>
