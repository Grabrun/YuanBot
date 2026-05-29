<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NTag, NButton } from 'naive-ui'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const providers = ref<any[]>([])
const activeProvider = ref('')

onMounted(async () => {
  await loadProviders()
})

async function loadProviders() {
  loading.value = true
  try {
    const data: any[] = await api.listProviders()
    providers.value = data
    const active = data.find((p: any) => p.is_default)
    if (active) activeProvider.value = active.provider_id
  } catch (e: any) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const columns = [
  { title: 'Provider ID', key: 'provider_id', width: 140 },
  {
    title: '名称',
    key: 'name',
    width: 120,
  },
  {
    title: '适配器',
    key: 'adapter',
    width: 150,
    render: (row: any) => h(NTag, { size: 'small', type: 'info' }, { default: () => row.adapter }),
  },
  {
    title: '默认模型',
    key: 'default_model',
    width: 160,
  },
  {
    title: '模型数',
    key: 'model_count',
    width: 80,
    render: (row: any) => row.models?.length || 0,
  },
  {
    title: '状态',
    key: 'enabled',
    width: 80,
    render: (row: any) =>
      h(
        NTag,
        { size: 'small', type: row.enabled ? 'success' : 'default' },
        { default: () => (row.enabled ? '启用' : '禁用') }
      ),
  },
  {
    title: '默认',
    key: 'is_default',
    width: 80,
    render: (row: any) =>
      row.is_default
        ? h(NTag, { size: 'small', type: 'warning' }, { default: () => '⭐ 默认' })
        : '',
  },
]
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px; margin-left: 16px">🔌 Provider 管理</n-text>
    </n-layout-header>

    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <n-card title="AI 提供商列表">
          <template #header-extra>
            <n-button @click="loadProviders" secondary>🔄 刷新</n-button>
          </template>
          <n-data-table :columns="columns" :data="providers" :bordered="false" />
        </n-card>

        <n-card title="配置说明" style="margin-top: 16px">
          <n-text>
            Provider 配置文件位于 <n-text code>configs/Providers/</n-text> 目录。
            每个 YAML 文件定义一个提供商，包含适配器类型、API 密钥、模型列表和默认模型。
          </n-text>
          <n-divider />
          <n-space vertical>
            <n-text>• 通过 <n-text code>bot.yaml</n-text> 的 <n-text code>ai.default_provider</n-text> 切换默认提供商</n-text>
            <n-text>• API Key 支持环境变量注入：<n-text code>${ENV_VAR}</n-text></n-text>
            <n-text>• 修改配置后可通过热加载生效，无需重启服务</n-text>
          </n-space>
        </n-card>
      </template>
    </n-layout-content>
  </n-layout>
</template>
