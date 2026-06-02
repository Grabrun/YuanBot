<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/client'

const router = useRouter()
const message = useMessage()

// ── State ────────────────────────────────────
const loading = ref(true)
const activeTab = ref<'my' | 'store'>('my')
const searchQuery = ref('')
const localPersonas = ref<any[]>([])
const marketplacePersonas = ref<any[]>([])
const activePersonaId = ref('')
const drawerVisible = ref(false)
const selectedPersona = ref<any>(null)
const installing = ref<Set<string>>(new Set())
const activating = ref<Set<string>>(new Set())

// ── Computed ─────────────────────────────────
const filteredLocal = computed(() => {
  if (!searchQuery.value) return localPersonas.value
  const q = searchQuery.value.toLowerCase()
  return localPersonas.value.filter(
    (p) =>
      p.name?.toLowerCase().includes(q) ||
      p.id?.toLowerCase().includes(q)
  )
})

const filteredMarketplace = computed(() => {
  if (!searchQuery.value) return marketplacePersonas.value
  const q = searchQuery.value.toLowerCase()
  return marketplacePersonas.value.filter(
    (p) =>
      p.name?.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q) ||
      p.id?.toLowerCase().includes(q) ||
      p.keywords?.some((k: string) => k.toLowerCase().includes(q))
  )
})

// ── Lifecycle ────────────────────────────────
onMounted(async () => {
  await loadData()
})

// ── Methods ──────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [personasData, activeData] = await Promise.all([
      api.listAllPersonas(),
      api.getActivePersona(),
    ])
    localPersonas.value = personasData.local || []
    marketplacePersonas.value = personasData.marketplace || []
    activePersonaId.value = activeData.persona_id || 'default'
  } catch (e: any) {
    message.error('加载人设数据失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function openDetail(persona: any) {
  selectedPersona.value = persona
  drawerVisible.value = true
}

function isLocal(persona: any): boolean {
  return localPersonas.value.some((p) => p.id === persona.id)
}

function isActive(persona: any): boolean {
  return persona.id === activePersonaId.value || persona.is_active
}

async function installPersona(personaId: string) {
  installing.value.add(personaId)
  try {
    await api.installPersona(personaId)
    message.success('人设安装成功')
    await loadData()
  } catch (e: any) {
    message.error('安装失败: ' + (e.message || '未知错误'))
  } finally {
    installing.value.delete(personaId)
  }
}

async function activatePersona(personaId: string) {
  activating.value.add(personaId)
  try {
    await api.activatePersona(personaId)
    activePersonaId.value = personaId
    message.success('人设切换成功')
    await loadData()
  } catch (e: any) {
    message.error('切换失败: ' + (e.message || '未知错误'))
  } finally {
    activating.value.delete(personaId)
  }
}

async function deletePersona(personaId: string) {
  try {
    await api.deletePersona(personaId)
    message.success('人设已删除')
    await loadData()
  } catch (e: any) {
    message.error('删除失败: ' + (e.message || '未知错误'))
  }
}

function getPersonaIcon(persona: any): string {
  const id = persona.id || ''
  if (id.includes('cheerful') || id.includes('happy')) return '😊'
  if (id.includes('gentle') || id.includes('soft')) return '🌸'
  if (id.includes('mentor') || id.includes('teacher')) return '📚'
  if (id.includes('creative') || id.includes('story')) return '🎨'
  if (id.includes('default') || id.includes('小缘')) return '💕'
  return '🤖'
}

function getPersonaColor(persona: any): string {
  const id = persona.id || ''
  if (id.includes('cheerful')) return '#ffb347'
  if (id.includes('gentle')) return '#ff9999'
  if (id.includes('mentor')) return '#87ceeb'
  if (id.includes('creative')) return '#dda0dd'
  return '#ffd1dc'
}
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center; gap: 16px">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px">🎭 人格商店</n-text>
    </n-layout-header>

    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <!-- 搜索栏 + Tab 切换 -->
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; flex-wrap: wrap">
          <n-tabs v-model:value="activeTab" type="segment" style="flex-shrink: 0">
            <n-tab-pane name="my" :tab="`💕 我的人设 (${localPersonas.length})`" />
            <n-tab-pane name="store" :tab="`🏪 商店 (${marketplacePersonas.length})`" />
          </n-tabs>
          <n-input
            v-model:value="searchQuery"
            placeholder="搜索人设..."
            clearable
            style="flex: 1; min-width: 200px"
          >
            <template #prefix>🔍</template>
          </n-input>
          <n-button @click="loadData" secondary>🔄 刷新</n-button>
        </div>

        <!-- 我的人设 Tab -->
        <template v-if="activeTab === 'my'">
          <n-empty v-if="filteredLocal.length === 0" description="暂无已安装人设" style="margin-top: 80px" />

          <n-grid v-else :x-gap="16" :y-gap="16" :cols="2" responsive="screen" item-responsive>
            <n-gi v-for="persona in filteredLocal" :key="persona.id">
              <n-card
                hoverable
                style="cursor: pointer; height: 100%"
                :style="isActive(persona) ? 'border: 2px solid #18a058' : ''"
                @click="openDetail(persona)"
              >
                <template #header>
                  <div style="display: flex; align-items: center; gap: 12px">
                    <div
                      style="
                        width: 48px;
                        height: 48px;
                        border-radius: 12px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 24px;
                      "
                      :style="{ background: getPersonaColor(persona) + '30' }"
                    >
                      {{ getPersonaIcon(persona) }}
                    </div>
                    <div>
                      <n-text strong>{{ persona.name || persona.id }}</n-text>
                      <div style="display: flex; gap: 6px; margin-top: 4px">
                        <n-tag v-if="isActive(persona)" type="success" size="small">使用中</n-tag>
                        <n-tag v-if="persona.is_default" type="info" size="small">默认</n-tag>
                      </div>
                    </div>
                  </div>
                </template>

                <n-text depth="3" style="font-size: 13px; display: block; margin-bottom: 12px">
                  {{ persona.system_prompt_preview || '暂无描述' }}
                </n-text>

                <div v-if="persona.capability_domains?.length" style="margin-bottom: 12px">
                  <n-tag
                    v-for="domain in persona.capability_domains.slice(0, 3)"
                    :key="domain"
                    size="small"
                    style="margin-right: 4px; margin-bottom: 4px"
                  >
                    {{ domain }}
                  </n-tag>
                </div>

                <template #action>
                  <n-space justify="end">
                    <n-button
                      v-if="!isActive(persona)"
                      type="primary"
                      size="small"
                      :loading="activating.has(persona.id)"
                      @click.stop="activatePersona(persona.id)"
                    >
                      切换
                    </n-button>
                    <n-button
                      v-if="!persona.is_default && !isActive(persona)"
                      type="error"
                      size="small"
                      @click.stop="deletePersona(persona.id)"
                    >
                      删除
                    </n-button>
                  </n-space>
                </template>
              </n-card>
            </n-gi>
          </n-grid>
        </template>

        <!-- 商店 Tab -->
        <template v-if="activeTab === 'store'">
          <n-empty v-if="filteredMarketplace.length === 0" description="商店暂无人设" style="margin-top: 80px" />

          <n-grid v-else :x-gap="16" :y-gap="16" :cols="3" responsive="screen" item-responsive>
            <n-gi v-for="persona in filteredMarketplace" :key="persona.id">
              <n-card
                hoverable
                style="cursor: pointer; height: 100%"
                @click="openDetail(persona)"
              >
                <template #header>
                  <div style="display: flex; align-items: center; gap: 12px">
                    <div
                      style="
                        width: 48px;
                        height: 48px;
                        border-radius: 12px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 24px;
                      "
                      :style="{ background: getPersonaColor(persona) + '30' }"
                    >
                      {{ getPersonaIcon(persona) }}
                    </div>
                    <div>
                      <n-text strong>{{ persona.name || persona.id }}</n-text>
                      <div style="display: flex; gap: 6px; margin-top: 4px">
                        <n-tag v-if="persona.is_installed" type="success" size="small">已安装</n-tag>
                        <n-tag v-if="persona.author" size="small">{{ persona.author }}</n-tag>
                      </div>
                    </div>
                  </div>
                </template>

                <n-text depth="3" style="font-size: 13px; display: block; margin-bottom: 12px">
                  {{ persona.description || '暂无描述' }}
                </n-text>

                <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 8px">
                  <n-rate :value="persona.rating || 0" :count="5" readonly size="small" />
                  <n-text depth="3" style="font-size: 12px">
                    {{ persona.rating ? persona.rating.toFixed(1) : '暂无评分' }}
                    <span v-if="persona.review_count">({{ persona.review_count }})</span>
                  </n-text>
                </div>

                <div style="display: flex; align-items: center; gap: 8px">
                  <n-text depth="3" style="font-size: 12px">
                    ⬇ {{ persona.downloads || 0 }} 次下载
                  </n-text>
                  <n-text v-if="persona.version" depth="3" style="font-size: 12px">
                    v{{ persona.version }}
                  </n-text>
                </div>

                <template #action>
                  <n-space justify="end">
                    <n-button
                      v-if="persona.is_installed"
                      type="primary"
                      size="small"
                      :loading="activating.has(persona.id)"
                      @click.stop="activatePersona(persona.id)"
                    >
                      激活
                    </n-button>
                    <n-button
                      v-else
                      type="primary"
                      size="small"
                      :loading="installing.has(persona.id)"
                      @click.stop="installPersona(persona.id)"
                    >
                      安装
                    </n-button>
                  </n-space>
                </template>
              </n-card>
            </n-gi>
          </n-grid>
        </template>
      </template>
    </n-layout-content>

    <!-- 详情抽屉 -->
    <n-drawer v-model:show="drawerVisible" :width="480" placement="right">
      <n-drawer-content v-if="selectedPersona" closable>
        <template #header>
          <div style="display: flex; align-items: center; gap: 12px">
            <div
              style="
                width: 56px;
                height: 56px;
                border-radius: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 28px;
              "
              :style="{ background: getPersonaColor(selectedPersona) + '30' }"
            >
              {{ getPersonaIcon(selectedPersona) }}
            </div>
            <div>
              <n-text strong style="font-size: 18px">
                {{ selectedPersona.name || selectedPersona.id }}
              </n-text>
              <div style="display: flex; gap: 6px; margin-top: 4px">
                <n-tag v-if="isActive(selectedPersona)" type="success" size="small">使用中</n-tag>
                <n-tag v-if="selectedPersona.is_installed || isLocal(selectedPersona)" type="info" size="small">
                  已安装
                </n-tag>
                <n-tag v-else type="warning" size="small">未安装</n-tag>
                <n-tag v-if="selectedPersona.version" size="small">v{{ selectedPersona.version }}</n-tag>
              </div>
            </div>
          </div>
        </template>

        <!-- 基本信息 -->
        <n-card title="📋 基本信息" size="small" style="margin-bottom: 16px">
          <n-descriptions :column="1" label-placement="left" bordered size="small">
            <n-descriptions-item label="ID">{{ selectedPersona.id }}</n-descriptions-item>
            <n-descriptions-item label="作者">{{ selectedPersona.author || '未知' }}</n-descriptions-item>
            <n-descriptions-item label="版本">{{ selectedPersona.version || '-' }}</n-descriptions-item>
            <n-descriptions-item label="下载量">{{ selectedPersona.downloads || 0 }}</n-descriptions-item>
            <n-descriptions-item v-if="selectedPersona.homepage" label="主页">
              <n-a :href="selectedPersona.homepage" target="_blank">{{ selectedPersona.homepage }}</n-a>
            </n-descriptions-item>
          </n-descriptions>
        </n-card>

        <!-- 描述 -->
        <n-card title="📝 描述" size="small" style="margin-bottom: 16px">
          <n-text>
            {{ selectedPersona.description || selectedPersona.system_prompt_preview || '暂无描述' }}
          </n-text>
        </n-card>

        <!-- 能力域 -->
        <n-card
          v-if="selectedPersona.capability_domains?.length"
          title="🎯 能力域"
          size="small"
          style="margin-bottom: 16px"
        >
          <n-space>
            <n-tag v-for="domain in selectedPersona.capability_domains" :key="domain" type="info">
              {{ domain }}
            </n-tag>
          </n-space>
        </n-card>

        <!-- 评分 -->
        <n-card title="⭐ 评分" size="small" style="margin-bottom: 16px">
          <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px">
            <n-rate :value="selectedPersona.rating || 0" :count="5" readonly size="small" />
            <n-text strong style="font-size: 16px">
              {{ selectedPersona.rating ? selectedPersona.rating.toFixed(1) : '暂无' }}
            </n-text>
            <n-text v-if="selectedPersona.review_count" depth="3">
              ({{ selectedPersona.review_count }} 条评论)
            </n-text>
          </div>
        </n-card>

        <!-- 关键词 -->
        <n-card
          v-if="selectedPersona.keywords?.length"
          title="🏷️ 标签"
          size="small"
          style="margin-bottom: 16px"
        >
          <n-space>
            <n-tag v-for="kw in selectedPersona.keywords" :key="kw" size="small">{{ kw }}</n-tag>
          </n-space>
        </n-card>

        <template #footer>
          <n-space justify="end" style="width: 100%">
            <n-button @click="drawerVisible = false">关闭</n-button>
            <n-button
              v-if="isLocal(selectedPersona) && !isActive(selectedPersona)"
              type="error"
              @click="deletePersona(selectedPersona.id); drawerVisible = false"
            >
              删除
            </n-button>
            <n-button
              v-if="isLocal(selectedPersona) && !isActive(selectedPersona)"
              type="primary"
              :loading="activating.has(selectedPersona.id)"
              @click="activatePersona(selectedPersona.id)"
            >
              切换为此人设
            </n-button>
            <n-button
              v-if="!isLocal(selectedPersona)"
              type="primary"
              :loading="installing.has(selectedPersona.id)"
              @click="installPersona(selectedPersona.id)"
            >
              安装
            </n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </n-layout>
</template>
