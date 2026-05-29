<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const activeTab = ref('facts')
const factMemories = ref<any[]>([])
const episodicMemories = ref<any[]>([])
const userProfiles = ref<any[]>([])
const searchQuery = ref('')

const filteredFacts = computed(() => {
  if (!searchQuery.value) return factMemories.value
  const q = searchQuery.value.toLowerCase()
  return factMemories.value.filter(
    (m) => m.key?.toLowerCase().includes(q) || m.value?.toLowerCase().includes(q)
  )
})

const filteredEpisodic = computed(() => {
  if (!searchQuery.value) return episodicMemories.value
  const q = searchQuery.value.toLowerCase()
  return episodicMemories.value.filter(
    (m) => m.summary?.toLowerCase().includes(q) || m.topic?.toLowerCase().includes(q)
  )
})

onMounted(async () => {
  await loadMemories()
})

async function loadMemories() {
  loading.value = true
  try {
    const data = await api.request<any>('/api/memory/overview')
    factMemories.value = data.fact_memories || []
    episodicMemories.value = data.episodic_memories || []
    userProfiles.value = data.user_profiles || []
  } catch (e: any) {
    // API 可能未实现，使用模拟数据
    message.warning('记忆 API 暂未开放，显示示例数据')
    factMemories.value = [
      { key: 'favorite_color', value: '蓝色', confidence: 0.9, updated_at: '2026-05-28' },
      { key: 'birthday', value: '1995-08-15', confidence: 1.0, updated_at: '2026-05-20' },
      { key: 'pet_name', value: '小橘', confidence: 0.85, updated_at: '2026-05-25' },
    ]
    episodicMemories.value = [
      { summary: '聊了关于工作的压力', topic: '工作', emotion: '焦虑', timestamp: '2026-05-28T20:00:00' },
      { summary: '讨论了周末去哪里玩', topic: '旅行', emotion: '开心', timestamp: '2026-05-27T15:30:00' },
    ]
    userProfiles.value = [
      { user_id: 'user1', nickname: '主人', relationship_stage: '亲密', interaction_count: 156 },
    ]
  } finally {
    loading.value = false
  }
}

async function handleDeleteFact(key: string) {
  try {
    await api.request(`/api/memory/facts/${key}`, { method: 'DELETE' })
    factMemories.value = factMemories.value.filter((m) => m.key !== key)
    message.success('已删除')
  } catch (e: any) {
    message.error(e.message || '删除失败')
  }
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN')
}
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px; margin-left: 16px">🧠 记忆浏览器</n-text>
    </n-layout-header>

    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <n-input
          v-model:value="searchQuery"
          placeholder="搜索记忆..."
          clearable
          style="margin-bottom: 16px"
        />

        <n-tabs v-model:value="activeTab" type="line" animated>
          <!-- 事实记忆 -->
          <n-tab-pane name="facts" :tab="`📚 事实记忆 (${factMemories.length})`">
            <n-data-table
              :columns="[
                { title: '键', key: 'key', width: 160 },
                { title: '值', key: 'value', ellipsis: { tooltip: true } },
                { title: '置信度', key: 'confidence', width: 100, render: (row: any) => `${(row.confidence * 100).toFixed(0)}%` },
                { title: '更新时间', key: 'updated_at', width: 160, render: (row: any) => formatTime(row.updated_at) },
                {
                  title: '操作',
                  key: 'actions',
                  width: 80,
                  render: (row: any) => h('n-button', { text: true, type: 'error', size: 'small', onClick: () => handleDeleteFact(row.key) }, () => '删除'),
                },
              ]"
              :data="filteredFacts"
              :bordered="false"
              :max-height="400"
            />
          </n-tab-pane>

          <!-- 情景记忆 -->
          <n-tab-pane name="episodic" :tab="`📖 情景记忆 (${episodicMemories.length})`">
            <n-timeline style="margin-top: 16px">
              <n-timeline-item
                v-for="(mem, idx) in filteredEpisodic"
                :key="idx"
                :title="mem.topic || '对话'"
                :content="mem.summary"
                :time="formatTime(mem.timestamp)"
                :type="mem.emotion === '开心' ? 'success' : mem.emotion === '焦虑' ? 'warning' : 'info'"
              />
            </n-timeline>
          </n-tab-pane>

          <!-- 用户画像 -->
          <n-tab-pane name="profiles" :tab="`👤 用户画像 (${userProfiles.length})`">
            <n-grid :cols="2" :x-gap="16" :y-gap="16" style="margin-top: 16px">
              <n-gi v-for="profile in userProfiles" :key="profile.user_id">
                <n-card :title="profile.nickname || profile.user_id">
                  <n-descriptions :column="1" bordered>
                    <n-descriptions-item label="关系阶段">
                      <n-tag :type="profile.relationship_stage === '亲密' ? 'error' : profile.relationship_stage === '熟悉' ? 'warning' : 'info'">
                        {{ profile.relationship_stage }}
                      </n-tag>
                    </n-descriptions-item>
                    <n-descriptions-item label="交互次数">
                      {{ profile.interaction_count }}
                    </n-descriptions-item>
                  </n-descriptions>
                </n-card>
              </n-gi>
            </n-grid>
          </n-tab-pane>
        </n-tabs>
      </template>
    </n-layout-content>
  </n-layout>
</template>

<script lang="ts">
import { h } from 'vue'
export default { name: 'MemoryView' }
</script>
