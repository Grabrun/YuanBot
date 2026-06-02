<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import * as echarts from 'echarts'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const activeTab = ref('facts')
const isMobile = ref(window.innerWidth <= 768)
const factMemories = ref<any[]>([])
const episodicMemories = ref<any[]>([])
const userProfiles = ref<any[]>([])
const searchQuery = ref('')
const graphChart = ref<echarts.ECharts | null>(null)
const graphContainer = ref<HTMLDivElement | null>(null)
const graphLoading = ref(false)
const graphDepth = ref(2)
const graphData = ref<any>(null)
const selectedNode = ref<any>(null)

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

const nodeColors: Record<string, string> = {
  User: '#18a058',
  Entity: '#2080f0',
  Event: '#f0a020',
  AIPersona: '#d03050',
}

const categoryMap: Record<number, string> = {
  0: 'User',
  1: 'Entity',
  2: 'Event',
  3: 'AIPersona',
}

onMounted(async () => {
  await loadMemories()
})

onBeforeUnmount(() => {
  graphChart.value?.dispose()
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

async function loadGraph() {
  graphLoading.value = true
  selectedNode.value = null
  try {
    const data = await api.request<any>(
      `/api/memory/graph?depth=${graphDepth.value}`
    )
    graphData.value = data
    await nextTick()
    renderGraph()
  } catch (e: any) {
    message.warning('图谱 API 暂未开放或数据为空')
    graphData.value = { nodes: [], links: [], categories: [] }
  } finally {
    graphLoading.value = false
  }
}

function renderGraph() {
  if (!graphContainer.value || !graphData.value) return

  if (!graphChart.value) {
    graphChart.value = echarts.init(graphContainer.value)
  }

  const { nodes, links, categories } = graphData.value

  // 增强节点样式
  const styledNodes = (nodes || []).map((n: any) => {
    const catName = categoryMap[n.category] || 'Entity'
    const color = nodeColors[catName] || '#2080f0'
    return {
      ...n,
      itemStyle: {
        color,
        borderColor: n.isCenter ? '#fff' : color,
        borderWidth: n.isCenter ? 3 : 1,
        shadowBlur: n.isCenter ? 20 : 0,
        shadowColor: n.isCenter ? color : 'transparent',
      },
      label: {
        show: true,
        formatter: '{b}',
        fontSize: n.isCenter ? 14 : 11,
        fontWeight: n.isCenter ? 'bold' : 'normal',
      },
    }
  })

  const styledLinks = (links || []).map((l: any) => ({
    ...l,
    lineStyle: {
      color: '#aaa',
      curveness: 0.2,
    },
    label: {
      show: true,
      formatter: l.relation || '',
      fontSize: 9,
      color: '#666',
    },
  }))

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          const d = params.data
          const cat = categoryMap[d.category] || 'Unknown'
          return `<div style="max-width:260px">
            <strong>${d.name}</strong><br/>
            <span style="color:${nodeColors[cat] || '#666'}">● ${cat}</span><br/>
            ${d.properties ? Object.entries(d.properties)
              .filter(([k]: any) => k !== 'name')
              .map(([k, v]: any) => `${k}: ${v}`)
              .join('<br/>') : ''}
          </div>`
        }
        if (params.dataType === 'edge') {
          return `${params.data.relation || ''}`
        }
        return ''
      },
    },
    legend: {
      data: ['User', 'Entity', 'Event', 'AIPersona'],
      top: 10,
      right: 10,
      orient: 'vertical',
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: styledNodes,
        links: styledLinks,
        categories: categories || [],
        roam: true,
        draggable: true,
        force: {
          repulsion: 200,
          gravity: 0.1,
          edgeLength: [80, 200],
          layoutAnimation: true,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
        },
        scaleLimit: { min: 0.3, max: 5 },
        lineStyle: { opacity: 0.8 },
      },
    ],
  }

  graphChart.value.setOption(option, true)

  graphChart.value.off('click')
  graphChart.value.on('click', (params: any) => {
    if (params.dataType === 'node') {
      selectedNode.value = params.data
    }
  })
}

function handleGraphResize() {
  graphChart.value?.resize()
}

watch(activeTab, async (tab) => {
  if (tab === 'graph') {
    await nextTick()
    if (!graphData.value) {
      await loadGraph()
    } else {
      handleGraphResize()
    }
  }
})

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
            <n-grid :cols="isMobile ? 1 : 2" :x-gap="16" :y-gap="16" style="margin-top: 16px">
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

          <!-- 知识图谱 -->
          <n-tab-pane name="graph" tab="🕸️ 知识图谱">
            <div style="margin-top: 8px">
              <!-- 工具栏 -->
              <n-space justify="space-between" align="center" style="margin-bottom: 12px">
                <n-space align="center">
                  <n-text depth="3" style="font-size: 13px">遍历深度</n-text>
                  <n-radio-group v-model:value="graphDepth" size="small">
                    <n-radio-button :value="1">1</n-radio-button>
                    <n-radio-button :value="2">2</n-radio-button>
                    <n-radio-button :value="3">3</n-radio-button>
                  </n-radio-group>
                </n-space>
                <n-button size="small" :loading="graphLoading" @click="loadGraph">
                  🔄 刷新
                </n-button>
              </n-space>

              <!-- 图谱容器 -->
              <div style="position: relative">
                <div
                  ref="graphContainer"
                  :style="{
                    width: '100%',
                    height: isMobile ? '350px' : '500px',
                    border: '1px solid var(--n-border-color)',
                    borderRadius: '8px',
                    background: 'var(--n-card-color)',
                  }"
                />
                <n-spin
                  v-if="graphLoading"
                  size="large"
                  :style="{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                  }"
                />
                <n-empty
                  v-if="!graphLoading && graphData && graphData.nodes.length === 0"
                  description="暂无图谱数据"
                  :style="{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                  }"
                />
              </div>

              <!-- 节点详情面板 -->
              <n-collapse-transition
                :show="!!selectedNode"
                style="margin-top: 12px"
              >
                <n-card
                  v-if="selectedNode"
                  size="small"
                  :title="`${selectedNode.name} 的详情`"
                  :bordered="true"
                  closable
                  @close="selectedNode = null"
                >
                  <n-descriptions :column="isMobile ? 1 : 2" bordered size="small">
                    <n-descriptions-item label="类型">
                      <n-tag
                        :color="{
                          color: nodeColors[categoryMap[selectedNode.category]] || '#2080f0',
                          textColor: '#fff',
                        }"
                        size="small"
                      >
                        {{ categoryMap[selectedNode.category] || 'Unknown' }}
                      </n-tag>
                    </n-descriptions-item>
                    <n-descriptions-item label="ID">
                      <n-text code style="font-size: 12px">{{ selectedNode.id }}</n-text>
                    </n-descriptions-item>
                    <n-descriptions-item
                      v-for="(val, key) in (selectedNode.properties || {})"
                      :key="key"
                      :label="String(key)"
                    >
                      {{ val }}
                    </n-descriptions-item>
                  </n-descriptions>
                </n-card>
              </n-collapse-transition>
            </div>
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
