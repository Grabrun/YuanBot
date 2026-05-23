<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { api } from '../api/client'

const message = useMessage()
const metrics = ref<Record<string, any> | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    metrics.value = await api.getMetrics()
  } catch (e: any) {
    message.error('加载管理数据失败')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <n-layout style="height: 100vh; padding: 24px">
    <n-page-header title="管理面板" subtitle="系统管理与监控" />

    <n-spin v-if="loading" size="large" style="margin-top: 40%; display: flex; justify-content: center" />

    <template v-else-if="metrics">
      <n-grid :cols="4" :x-gap="16" :y-gap="16" style="margin-top: 24px">
        <n-gi>
          <n-card title="用户数">
            <n-statistic :value="metrics.yuanbot?.users?.total || 0" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="会话数">
            <n-statistic :value="metrics.yuanbot?.conversations?.total || 0" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="消息总数">
            <n-statistic :value="metrics.yuanbot?.conversations?.messages || 0" />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="CPU 使用率">
            <n-statistic :value="metrics.system?.cpu_percent || 0" suffix="%" />
          </n-card>
        </n-gi>
      </n-grid>

      <n-grid :cols="2" :x-gap="16" style="margin-top: 16px">
        <n-gi>
          <n-card title="系统信息">
            <n-descriptions :column="1" bordered>
              <n-descriptions-item label="Python">
                {{ metrics.system?.python_version?.split(' ')[0] }}
              </n-descriptions-item>
              <n-descriptions-item label="内存使用">
                {{ metrics.system?.memory?.used_percent || 0 }}%
              </n-descriptions-item>
              <n-descriptions-item label="磁盘使用">
                {{ metrics.system?.disk?.used_percent || 0 }}%
              </n-descriptions-item>
            </n-descriptions>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="AI 提供商">
            <n-text depth="3">在「聊天」页面可查看和切换提供商</n-text>
          </n-card>
        </n-gi>
      </n-grid>
    </template>
  </n-layout>
</template>
