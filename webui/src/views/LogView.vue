<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'

const router = useRouter()

const logs = ref<{ time: string; level: string; module: string; msg: string; raw: string }[]>([])
const autoScroll = ref(true)
const levelFilter = ref<string>('all')
const searchQuery = ref('')
const wsConnected = ref(false)
let ws: WebSocket | null = null
let logContainer: HTMLElement | null = null

const filteredLogs = () => {
  let result = logs.value
  if (levelFilter.value !== 'all') {
    result = result.filter((l) => l.level === levelFilter.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter((l) => l.raw.toLowerCase().includes(q))
  }
  return result
}

function connectLogStream() {
  const token = api.getToken()
  const wsBase = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  const url = `${wsBase}/ws/logs?token=${token}`

  ws = new WebSocket(url)

  ws.onopen = () => {
    wsConnected.value = true
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'log') {
        const entry = {
          time: data.timestamp || new Date().toISOString(),
          level: data.level || 'info',
          module: data.module || '',
          msg: data.message || data.msg || '',
          raw: event.data,
        }
        logs.value.push(entry)
        // 限制最大 2000 条
        if (logs.value.length > 2000) {
          logs.value = logs.value.slice(-1500)
        }
        if (autoScroll.value) {
          nextTick(() => {
            if (logContainer) {
              logContainer.scrollTop = logContainer.scrollHeight
            }
          })
        }
      }
    } catch {
      // 非 JSON 消息
      logs.value.push({
        time: new Date().toISOString(),
        level: 'info',
        module: '',
        msg: event.data,
        raw: event.data,
      })
    }
  }

  ws.onclose = () => {
    wsConnected.value = false
    // 3 秒后重连
    setTimeout(connectLogStream, 3000)
  }

  ws.onerror = () => {
    wsConnected.value = false
  }
}

function clearLogs() {
  logs.value = []
}

function getLevelColor(level: string) {
  switch (level) {
    case 'error': return '#e74c3c'
    case 'warning': return '#f39c12'
    case 'info': return '#3498db'
    case 'debug': return '#95a5a6'
    default: return '#7f8c8d'
  }
}

function formatTime(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN')
  } catch {
    return ts
  }
}

onMounted(() => {
  connectLogStream()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
})
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center; gap: 16px">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px">📋 实时日志</n-text>
      <div style="flex: 1" />
      <n-tag :type="wsConnected ? 'success' : 'error'" size="small">
        {{ wsConnected ? '🟢 已连接' : '🔴 断开' }}
      </n-tag>
      <n-select
        v-model:value="levelFilter"
        :options="[
          { label: '全部', value: 'all' },
          { label: 'ERROR', value: 'error' },
          { label: 'WARNING', value: 'warning' },
          { label: 'INFO', value: 'info' },
          { label: 'DEBUG', value: 'debug' },
        ]"
        size="small"
        style="width: 120px"
      />
      <n-input v-model:value="searchQuery" placeholder="搜索日志..." size="small" clearable style="width: 200px" />
      <n-button size="small" @click="clearLogs">清空</n-button>
    </n-layout-header>

    <n-layout-content
      ref="logContainer"
      :native-scrollbar="false"
      style="height: calc(100vh - 56px); background: #1e1e1e; padding: 12px; font-family: 'Courier New', monospace; font-size: 13px"
    >
      <div
        v-for="(log, idx) in filteredLogs()"
        :key="idx"
        style="line-height: 1.6; white-space: pre-wrap; word-break: break-all"
      >
        <span style="color: #666">{{ formatTime(log.time) }}</span>
        <span :style="{ color: getLevelColor(log.level), fontWeight: 'bold', margin: '0 8px' }">
          [{{ log.level.toUpperCase() }}]
        </span>
        <span v-if="log.module" style="color: #9b59b6; margin-right: 8px">{{ log.module }}</span>
        <span style="color: #ecf0f1">{{ log.msg }}</span>
      </div>

      <n-empty v-if="filteredLogs().length === 0" description="等待日志..." style="color: #7f8c8d; margin-top: 20%" />
    </n-layout-content>
  </n-layout>
</template>
