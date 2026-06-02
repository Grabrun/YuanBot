<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/client'
import MarkdownIt from 'markdown-it'

const router = useRouter()
const message = useMessage()
const md = new MarkdownIt({ html: false, linkify: true, typographer: true })

// ── 状态 ──────────────────────────────────
const loading = ref(false)
const refreshing = ref(false)
const searchQuery = ref('')
const activeCategory = ref('all')
const categories = ref<Record<string, number>>({})
const extensions = ref<any[]>([])
const installedIds = ref<Set<string>>(new Set())

// 抽屉
const drawerVisible = ref(false)
const drawerLoading = ref(false)
const selectedExt = ref<any>(null)
const detailReadme = ref('')
const reviews = ref<any[]>([])
const reviewStats = ref<any>(null)
const installing = ref<string | null>(null)
const uninstalling = ref<string | null>(null)

// ── 分类 tabs ─────────────────────────────
const categoryTabs = computed(() => {
  const tabs = [{ label: '全部', value: 'all', count: 0 }]
  const cats = categories.value
  let total = 0
  for (const [type, count] of Object.entries(cats)) {
    total += count
    tabs.push({
      label: typeLabel(type),
      value: type,
      count,
    })
  }
  tabs[0].count = total
  return tabs
})

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    skill: 'Skills',
    tool: 'Tools',
    channel: 'Channels',
    persona: 'Personas',
    ai_provider: 'Providers',
    trigger: 'Triggers',
  }
  return map[type] || type
}

function typeTagType(type: string): string {
  const map: Record<string, string> = {
    skill: 'success',
    tool: 'warning',
    channel: 'info',
    persona: 'primary',
    ai_provider: 'error',
    trigger: 'default',
  }
  return map[type] || 'default'
}

// ── 加载数据 ──────────────────────────────
async function loadCategories() {
  try {
    const data = await api.marketplaceCategories()
    categories.value = data.categories || {}
  } catch {
    // ignore
  }
}

async function loadExtensions() {
  loading.value = true
  try {
    const data = await api.marketplaceSearch(
      searchQuery.value,
      activeCategory.value === 'all' ? '' : activeCategory.value,
    )
    extensions.value = data.extensions || []
  } catch (e: any) {
    message.error('加载市场数据失败: ' + (e.message || '未知错误'))
    extensions.value = []
  } finally {
    loading.value = false
  }
}

async function loadInstalled() {
  try {
    const data = await api.marketplaceInstalled()
    installedIds.value = new Set((data.installed || []).map((e: any) => e.id))
  } catch {
    // ignore
  }
}

async function refreshMarketplace() {
  refreshing.value = true
  try {
    await api.marketplaceRefresh()
    message.success('市场索引已刷新')
    await loadCategories()
    await loadExtensions()
  } catch (e: any) {
    message.error('刷新失败: ' + (e.message || '未知错误'))
  } finally {
    refreshing.value = false
  }
}

// ── 搜索防抖 ─────────────────────────────
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    loadExtensions()
  }, 300)
})

function onCategoryChange(val: string) {
  activeCategory.value = val
  loadExtensions()
}

// ── 抽屉详情 ──────────────────────────────
async function openDrawer(ext: any) {
  drawerVisible.value = true
  drawerLoading.value = true
  selectedExt.value = ext
  detailReadme.value = ''
  reviews.value = []
  reviewStats.value = null

  try {
    // 加载详情
    const detail = await api.marketplaceDetail(ext.id)
    selectedExt.value = detail

    // 尝试加载 README (如果有 homepage/repository 链接)
    if (detail.homepage) {
      try {
        const resp = await fetch(`https://api.allorigins.win/raw?url=${encodeURIComponent(detail.homepage)}`)
        if (resp.ok) {
          const text = await resp.text()
          detailReadme.value = text.slice(0, 10000)
        }
      } catch {
        // README 加载失败不是致命错误
      }
    }
  } catch (e: any) {
    message.error('加载扩展详情失败')
  }

  // 加载评论和统计
  try {
    const [reviewsData, statsData] = await Promise.all([
      api.marketplaceReviews(ext.id, 20, 0),
      api.marketplaceReviewStats(ext.id),
    ])
    reviews.value = reviewsData.reviews || []
    reviewStats.value = statsData
  } catch {
    // 评论加载失败不致命
  }

  drawerLoading.value = false
}

// ── 安装 / 卸载 ──────────────────────────
async function installExtension(extId: string) {
  installing.value = extId
  try {
    await api.marketplaceInstall(extId)
    message.success('安装成功')
    installedIds.value.add(extId)
  } catch (e: any) {
    message.error('安装失败: ' + (e.message || '未知错误'))
  } finally {
    installing.value = null
  }
}

async function uninstallExtension(extId: string) {
  uninstalling.value = extId
  try {
    await api.marketplaceUninstall(extId)
    message.success('已卸载')
    installedIds.value.delete(extId)
  } catch (e: any) {
    message.error('卸载失败: ' + (e.message || '未知错误'))
  } finally {
    uninstalling.value = null
  }
}

// ── 渲染辅助 ─────────────────────────────
function formatNumber(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function renderMarkdown(text: string): string {
  return md.render(text || '')
}

// ── 生命周期 ─────────────────────────────
onMounted(async () => {
  await Promise.all([loadCategories(), loadExtensions(), loadInstalled()])
})
</script>

<template>
  <n-layout style="height: 100vh">
    <!-- 顶部栏 -->
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap">
      <n-button text @click="router.push('/plugins')">← 返回插件</n-button>
      <n-text strong style="font-size: 18px">🛒 扩展市场</n-text>
      <div style="flex: 1" />
      <n-input
        v-model:value="searchQuery"
        placeholder="搜索扩展..."
        clearable
        style="max-width: 320px"
      >
        <template #prefix>🔍</template>
      </n-input>
      <n-button
        :loading="refreshing"
        @click="refreshMarketplace"
        secondary
      >
        🔄 刷新
      </n-button>
    </n-layout-header>

    <!-- 分类 Tabs -->
    <n-layout-header bordered style="padding: 0 24px">
      <n-tabs
        :value="activeCategory"
        type="line"
        animated
        @update:value="onCategoryChange"
      >
        <n-tab-pane
          v-for="tab in categoryTabs"
          :key="tab.value"
          :name="tab.value"
          :tab="`${tab.label} (${tab.count})`"
          :disabled="loading"
        />
      </n-tabs>
    </n-layout-header>

    <!-- 主内容区 -->
    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <!-- 空状态 -->
        <n-empty
          v-if="extensions.length === 0"
          description="没有找到扩展"
          style="margin-top: 20%"
        />

        <!-- 扩展卡片网格 -->
        <div v-else style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px">
          <n-card
            v-for="ext in extensions"
            :key="ext.id"
            hoverable
            style="cursor: pointer"
            @click="openDrawer(ext)"
          >
            <template #header>
              <div style="display: flex; align-items: center; gap: 8px">
                <n-avatar :size="32" :style="{ backgroundColor: '#18a058' }">
                  {{ (ext.name || ext.id || '?')[0].toUpperCase() }}
                </n-avatar>
                <n-text strong>{{ ext.name || ext.id }}</n-text>
              </div>
            </template>

            <template #header-extra>
              <n-tag v-if="installedIds.has(ext.id)" type="success" size="small">已安装</n-tag>
            </template>

            <n-text depth="3" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 40px">
              {{ ext.description || '暂无描述' }}
            </n-text>

            <template #footer>
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
                <n-tag :type="typeTagType(ext.type)" size="small">{{ typeLabel(ext.type) }}</n-tag>
                <n-text depth="3" style="font-size: 12px">v{{ ext.version }}</n-text>
                <n-text v-if="ext.author" depth="3" style="font-size: 12px">by {{ ext.author }}</n-text>
              </div>
            </template>

            <template #action>
              <div style="display: flex; align-items: center; justify-content: space-between">
                <div style="display: flex; align-items: center; gap: 12px">
                    <span style="font-size: 12px; color: #999">
                    ⭐ {{ ext.stars || 0 }}
                  </span>
                  <n-text depth="3" style="font-size: 12px">📥 {{ formatNumber(ext.downloads || 0) }}</n-text>
                </div>
                <n-button
                  v-if="installedIds.has(ext.id)"
                  size="small"
                  type="error"
                  secondary
                  :loading="uninstalling === ext.id"
                  @click.stop="uninstallExtension(ext.id)"
                >
                  卸载
                </n-button>
                <n-button
                  v-else
                  size="small"
                  type="primary"
                  :loading="installing === ext.id"
                  @click.stop="installExtension(ext.id)"
                >
                  安装
                </n-button>
              </div>
            </template>
          </n-card>
        </div>
      </template>
    </n-layout-content>

    <!-- 详情抽屉 -->
    <n-drawer
      v-model:show="drawerVisible"
      :width="560"
      placement="right"
    >
      <n-drawer-content closable>
        <template #header>
          <div style="display: flex; align-items: center; gap: 12px">
            <n-avatar :size="40" :style="{ backgroundColor: '#18a058' }">
              {{ (selectedExt?.name || selectedExt?.id || '?')[0].toUpperCase() }}
            </n-avatar>
            <div>
              <n-text strong style="font-size: 16px">{{ selectedExt?.name || selectedExt?.id }}</n-text>
              <br />
              <n-text depth="3" style="font-size: 12px">v{{ selectedExt?.version }} · by {{ selectedExt?.author || '未知' }}</n-text>
            </div>
          </div>
        </template>

        <n-spin v-if="drawerLoading" size="large" style="margin-top: 40%; display: flex; justify-content: center" />

        <template v-else-if="selectedExt">
          <n-scrollbar style="height: calc(100vh - 120px)">
            <div style="padding: 0 4px 16px">
              <!-- 操作栏 -->
              <div style="display: flex; gap: 8px; margin-bottom: 16px">
                <n-button
                  v-if="installedIds.has(selectedExt.id)"
                  type="error"
                  :loading="uninstalling === selectedExt.id"
                  @click="uninstallExtension(selectedExt.id)"
                >
                  卸载扩展
                </n-button>
                <n-button
                  v-else
                  type="primary"
                  :loading="installing === selectedExt.id"
                  @click="installExtension(selectedExt.id)"
                >
                  安装扩展
                </n-button>
                <n-tag v-if="installedIds.has(selectedExt.id)" type="success" style="align-self: center">已安装</n-tag>
              </div>

              <!-- 基本信息 -->
              <n-descriptions :column="2" bordered size="small" label-style="width: 80px">
                <n-descriptions-item label="分类">
                  <n-tag :type="typeTagType(selectedExt.type)" size="small">{{ typeLabel(selectedExt.type) }}</n-tag>
                </n-descriptions-item>
                <n-descriptions-item label="版本">v{{ selectedExt.version }}</n-descriptions-item>
                <n-descriptions-item label="作者">{{ selectedExt.author || '未知' }}</n-descriptions-item>
                <n-descriptions-item label="许可证">{{ selectedExt.license || '未知' }}</n-descriptions-item>
                <n-descriptions-item label="下载量">{{ formatNumber(selectedExt.downloads || 0) }}</n-descriptions-item>
                <n-descriptions-item label="星标">{{ selectedExt.stars || 0 }}</n-descriptions-item>
                <n-descriptions-item label="更新时间" :span="2">{{ selectedExt.updated_at || '未知' }}</n-descriptions-item>
              </n-descriptions>

              <!-- 描述 -->
              <n-card title="📝 描述" size="small" style="margin-top: 16px">
                <n-text>{{ selectedExt.description || '暂无描述' }}</n-text>
              </n-card>

              <!-- 关键词 -->
              <div v-if="selectedExt.keywords?.length" style="margin-top: 16px">
                <n-text strong style="margin-bottom: 8px; display: block">🏷️ 关键词</n-text>
                <n-space>
                  <n-tag v-for="kw in selectedExt.keywords" :key="kw" size="small">{{ kw }}</n-tag>
                </n-space>
              </div>

              <!-- 依赖信息 -->
              <n-card v-if="selectedExt.min_core_version" title="📦 依赖" size="small" style="margin-top: 16px">
                <n-text>最低核心版本: <n-text code>{{ selectedExt.min_core_version }}</n-text></n-text>
              </n-card>

              <!-- README -->
              <n-card v-if="detailReadme" title="📖 README" size="small" style="margin-top: 16px">
                <div v-html="renderMarkdown(detailReadme)" class="markdown-body" />
              </n-card>

              <!-- 链接 -->
              <div v-if="selectedExt.homepage || selectedExt.repository" style="margin-top: 16px">
                <n-text strong style="margin-bottom: 8px; display: block">🔗 链接</n-text>
                <n-space>
                  <n-button v-if="selectedExt.homepage" tag="a" :href="selectedExt.homepage" target="_blank" text type="primary">
                    🏠 主页
                  </n-button>
                  <n-button v-if="selectedExt.repository" tag="a" :href="selectedExt.repository" target="_blank" text type="primary">
                    📁 仓库
                  </n-button>
                </n-space>
              </div>

              <!-- 评分统计 -->
              <n-card title="⭐ 评分" size="small" style="margin-top: 16px">
                <template v-if="reviewStats && reviewStats.total_reviews > 0">
                  <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 12px">
                    <n-text style="font-size: 32px; font-weight: bold">{{ reviewStats.average_rating.toFixed(1) }}</n-text>
                    <div>
                      <n-rate :value="reviewStats.average_rating" readonly allow-half />
                      <n-text depth="3" style="display: block; font-size: 12px">{{ reviewStats.total_reviews }} 条评论</n-text>
                    </div>
                  </div>
                  <!-- 评分分布条形图 -->
                  <div v-for="star in [5, 4, 3, 2, 1]" :key="star" style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
                    <n-text style="width: 20px; text-align: right; font-size: 12px">{{ star }}★</n-text>
                    <n-progress
                      type="line"
                      :percentage="reviewStats.total_reviews > 0 ? (reviewStats.rating_distribution[star] / reviewStats.total_reviews) * 100 : 0"
                      :show-indicator="false"
                      style="flex: 1"
                    />
                    <n-text depth="3" style="width: 30px; font-size: 12px">{{ reviewStats.rating_distribution[star] || 0 }}</n-text>
                  </div>
                </template>
                <n-empty v-else description="暂无评论" size="small" />
              </n-card>

              <!-- 评论列表 -->
              <n-card title="💬 评论" size="small" style="margin-top: 16px">
                <template v-if="reviews.length > 0">
                  <n-list bordered>
                    <n-list-item v-for="review in reviews" :key="review.id">
                      <n-thing>
                        <template #header>
                          <div style="display: flex; align-items: center; gap: 8px">
                            <n-text strong>{{ review.user_id }}</n-text>
                            <n-rate :value="review.rating" readonly size="small" />
                          </div>
                        </template>
                        <template #header-extra>
                          <n-text depth="3" style="font-size: 12px">
                            {{ new Date(review.created_at * 1000).toLocaleDateString() }}
                          </n-text>
                        </template>
                        <n-text v-if="review.title" strong style="display: block; margin-bottom: 4px">{{ review.title }}</n-text>
                        <n-text>{{ review.content }}</n-text>
                        <template #footer>
                          <n-text depth="3" style="font-size: 12px">👍 {{ review.helpful_count }} 人觉得有帮助</n-text>
                        </template>
                      </n-thing>
                    </n-list-item>
                  </n-list>
                </template>
                <n-empty v-else description="暂无评论" size="small" />
              </n-card>
            </div>
          </n-scrollbar>
        </template>
      </n-drawer-content>
    </n-drawer>
  </n-layout>
</template>

<style scoped>
.markdown-body {
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
}
.markdown-body :deep(p) {
  margin-bottom: 8px;
}
.markdown-body :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 13px;
}
.markdown-body :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin-bottom: 8px;
}
.markdown-body :deep(a) {
  color: #18a058;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #18a058;
  padding-left: 12px;
  margin: 8px 0;
  color: #666;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 12px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #ddd;
  padding: 6px 12px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: rgba(0, 0, 0, 0.04);
}
</style>
