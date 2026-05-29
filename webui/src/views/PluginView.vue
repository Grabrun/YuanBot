<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NTag } from 'naive-ui'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const activeTab = ref('skills')
const skills = ref<any[]>([])
const tools = ref<any[]>([])

onMounted(async () => {
  await loadPlugins()
})

async function loadPlugins() {
  loading.value = true
  try {
    const data = await api.request<any>('/api/plugins')
    skills.value = data.skills || []
    tools.value = data.tools || []
  } catch (e: any) {
    message.warning('插件 API 暂未开放，显示示例数据')
    skills.value = [
      { skill_id: 'emotional_comfort', name: '情绪安抚', version: '1.0.0', category: 'emotional_care', enabled: true },
      { skill_id: 'daily_chat', name: '日常闲聊', version: '1.0.0', category: 'daily_chat', enabled: true },
      { skill_id: 'creative_storytelling', name: '创意故事', version: '1.0.0', category: 'creative_storytelling', enabled: true },
      { skill_id: 'bedtime_story', name: '睡前故事', version: '1.0.0', category: 'creative_storytelling', enabled: true },
    ]
    tools.value = [
      { tool_id: 'get_weather', name: '天气查询', version: '1.0.0', category: 'daily_chat', enabled: true, executor_type: 'local_thread' },
      { tool_id: 'set_reminder', name: '设置提醒', version: '1.0.0', category: 'daily_chat', enabled: true, executor_type: 'local_thread' },
      { tool_id: 'search', name: '联网搜索', version: '1.0.0', category: 'knowledge_query', enabled: true, executor_type: 'local_thread' },
    ]
  } finally {
    loading.value = false
  }
}

const skillColumns = [
  { title: 'ID', key: 'skill_id', width: 180 },
  { title: '名称', key: 'name', width: 120 },
  { title: '版本', key: 'version', width: 80 },
  {
    title: '分类',
    key: 'category',
    width: 140,
    render: (row: any) => h(NTag, { size: 'small' }, { default: () => row.category }),
  },
  {
    title: '状态',
    key: 'enabled',
    width: 80,
    render: (row: any) =>
      h(NTag, { size: 'small', type: row.enabled ? 'success' : 'default' }, { default: () => (row.enabled ? '启用' : '禁用') }),
  },
]

const toolColumns = [
  { title: 'ID', key: 'tool_id', width: 180 },
  { title: '名称', key: 'name', width: 120 },
  { title: '版本', key: 'version', width: 80 },
  {
    title: '分类',
    key: 'category',
    width: 140,
    render: (row: any) => h(NTag, { size: 'small', type: 'info' }, { default: () => row.category }),
  },
  {
    title: '执行器',
    key: 'executor_type',
    width: 120,
    render: (row: any) => h(NTag, { size: 'small', type: 'warning' }, { default: () => row.executor_type }),
  },
  {
    title: '状态',
    key: 'enabled',
    width: 80,
    render: (row: any) =>
      h(NTag, { size: 'small', type: row.enabled ? 'success' : 'default' }, { default: () => (row.enabled ? '启用' : '禁用') }),
  },
]
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px; margin-left: 16px">🧩 插件管理</n-text>
    </n-layout-header>

    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <n-tabs v-model:value="activeTab" type="line" animated>
          <n-tab-pane name="skills" :tab="`🎯 技能 (${skills.length})`">
            <n-card style="margin-top: 16px">
              <template #header-extra>
                <n-button @click="loadPlugins" secondary>🔄 刷新</n-button>
              </template>
              <n-data-table :columns="skillColumns" :data="skills" :bordered="false" />
            </n-card>
          </n-tab-pane>

          <n-tab-pane name="tools" :tab="`🔧 工具 (${tools.length})`">
            <n-card style="margin-top: 16px">
              <template #header-extra>
                <n-button @click="loadPlugins" secondary>🔄 刷新</n-button>
              </template>
              <n-data-table :columns="toolColumns" :data="tools" :bordered="false" />
            </n-card>
          </n-tab-pane>
        </n-tabs>

        <n-card title="插件目录" style="margin-top: 16px">
          <n-text>
            技能配置：<n-text code>configs/Plugins/skills/*.yaml</n-text><br />
            工具配置：<n-text code>configs/Plugins/tools/*.yaml</n-text><br />
            修改 YAML 文件后可通过热加载生效。
          </n-text>
        </n-card>
      </template>
    </n-layout-content>
  </n-layout>
</template>
