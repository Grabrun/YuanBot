<script setup lang="ts">
import { useChatStore } from '../stores/chat'
import { useDialog, useMessage } from 'naive-ui'

const chat = useChatStore()
const dialog = useDialog()
const message = useMessage()

function selectConv(convId: string) {
  chat.selectConversation(convId)
}

function deleteConv(convId: string, title: string) {
  dialog.warning({
    title: '删除会话',
    content: `确定要删除「${title}」吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await chat.deleteConversation(convId)
        message.success('已删除')
      } catch (e: any) {
        message.error(e.message || '删除失败')
      }
    },
  })
}
</script>

<template>
  <n-list hoverable clickable>
    <n-list-item
      v-for="conv in chat.conversations"
      :key="conv.conversation_id"
      :class="{ active: conv.conversation_id === chat.currentConvId }"
      @click="selectConv(conv.conversation_id)"
    >
      <n-thing>
        <template #header>
          <n-text :strong="conv.conversation_id === chat.currentConvId">
            {{ conv.title }}
          </n-text>
        </template>
        <template #header-extra>
          <n-button text type="error" size="small" @click.stop="deleteConv(conv.conversation_id, conv.title)">
            ×
          </n-button>
        </template>
        <template #description>
          <n-text depth="3" style="font-size: 12px">
            {{ conv.message_count }} 条 · {{ new Date(conv.updated_at).toLocaleDateString() }}
          </n-text>
        </template>
      </n-thing>
    </n-list-item>
  </n-list>
</template>

<style scoped>
.n-list-item.active {
  background: rgba(102, 126, 234, 0.1);
  border-left: 3px solid #667eea;
}
</style>
