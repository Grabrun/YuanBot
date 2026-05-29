<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const activeFile = ref('bot.yaml')
const editorContent = ref('')
const fileList = ref<string[]>([])

const configFiles = [
  { label: 'bot.yaml（根配置）', value: 'bot.yaml' },
  { label: 'database.yaml（数据库）', value: 'database.yaml' },
  { label: 'memory.yaml（记忆系统）', value: 'memory.yaml' },
  { label: 'extensions.yaml（扩展）', value: 'extensions.yaml' },
]

onMounted(async () => {
  await loadFileList()
  await loadConfig()
})

async function loadFileList() {
  try {
    const data = await api.request<any>('/api/admin/configs')
    fileList.value = data.files || configFiles.map((c) => c.value)
  } catch {
    fileList.value = configFiles.map((c) => c.value)
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await api.request<any>(`/api/admin/configs/${activeFile.value}`)
    editorContent.value = data.content || data.yaml || ''
  } catch {
    editorContent.value = `# ${activeFile.value}\n# 暂无法通过 API 读取，请直接编辑服务器上的文件\n`
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await api.request(`/api/admin/configs/${activeFile.value}`, {
      method: 'PUT',
      body: JSON.stringify({ content: editorContent.value }),
    })
    message.success('保存成功，热加载生效中...')
  } catch (e: any) {
    message.error(e.message || '保存失败，可能需要手动编辑服务器文件')
  } finally {
    saving.value = false
  }
}

function handleFileChange(file: string) {
  activeFile.value = file
  loadConfig()
}
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center; gap: 16px">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px">⚙️ 配置编辑器</n-text>
      <div style="flex: 1" />
      <n-select
        :value="activeFile"
        :options="configFiles"
        @update:value="handleFileChange"
        style="width: 240px"
      />
      <n-button type="primary" :loading="saving" @click="handleSave">💾 保存并热加载</n-button>
    </n-layout-header>

    <n-layout-content style="height: calc(100vh - 56px)">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />
      <div v-else style="height: 100%; display: flex; flex-direction: column">
        <n-input
          v-model:value="editorContent"
          type="textarea"
          :autosize="false"
          placeholder="YAML 配置内容..."
          style="flex: 1; font-family: 'Courier New', monospace; font-size: 14px"
          :input-props="{ style: { height: '100%', resize: 'none' } }"
        />
        <div style="padding: 8px 24px; background: var(--n-card-color); border-top: 1px solid var(--n-border-color)">
          <n-text depth="3" style="font-size: 12px">
            📁 文件路径：configs/{{ activeFile }} ｜ 修改后点击保存，系统将自动热加载配置
          </n-text>
        </div>
      </div>
    </n-layout-content>
  </n-layout>
</template>
