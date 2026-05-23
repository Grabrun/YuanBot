<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { api, type User } from '../api/client'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const metrics = ref<Record<string, any> | null>(null)
const users = ref<User[]>([])
const loading = ref(true)
const activeTab = ref('dashboard')
const showCreateUser = ref(false)
const newUser = ref({ username: '', password: '', display_name: '', role: 'user' as string })

onMounted(async () => {
  if (!auth.isAdmin) {
    router.push('/')
    return
  }
  await loadData()
})

async function loadData() {
  loading.value = true
  try {
    const [m, u] = await Promise.all([api.getMetrics(), api.listUsers()])
    metrics.value = m
    users.value = u.users
  } catch (e: any) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleCreateUser() {
  try {
    await api.createUser(
      newUser.value.username,
      newUser.value.password,
      newUser.value.display_name,
      newUser.value.role
    )
    message.success('用户创建成功')
    showCreateUser.value = false
    newUser.value = { username: '', password: '', display_name: '', role: 'user' }
    await loadData()
  } catch (e: any) {
    message.error(e.message || '创建失败')
  }
}

async function handleDeleteUser(userId: string, username: string) {
  dialog.warning({
    title: '删除用户',
    content: `确定要删除用户「${username}」吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteUser(userId)
        message.success('已删除')
        await loadData()
      } catch (e: any) {
        message.error(e.message || '删除失败')
      }
    },
  })
}

async function handleGenerateApiKey(userId: string) {
  try {
    const resp = await api.generateApiKey(userId)
    dialog.info({
      title: 'API Key',
      content: resp.api_key,
      positiveText: '确定',
    })
    await loadData()
  } catch (e: any) {
    message.error(e.message || '生成失败')
  }
}

async function handleBackup() {
  try {
    const resp = await api.triggerBackup()
    message.success(`备份完成: ${resp.backup}`)
  } catch (e: any) {
    message.error(e.message || '备份失败')
  }
}
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="padding: 12px 24px; display: flex; align-items: center">
      <n-button text @click="router.push('/')">← 返回聊天</n-button>
      <n-text strong style="font-size: 18px; margin-left: 16px">📊 管理面板</n-text>
    </n-layout-header>

    <n-layout-content style="padding: 24px" :native-scrollbar="false">
      <n-spin v-if="loading" size="large" style="margin-top: 20%; display: flex; justify-content: center" />

      <template v-else>
        <n-tabs v-model:value="activeTab" type="line" animated>
          <!-- 仪表盘 -->
          <n-tab-pane name="dashboard" tab="仪表盘">
            <n-grid :cols="4" :x-gap="16" :y-gap="16" style="margin-top: 16px">
              <n-gi>
                <n-card title="用户数">
                  <n-statistic :value="metrics?.yuanbot?.users?.total || 0" />
                </n-card>
              </n-gi>
              <n-gi>
                <n-card title="会话数">
                  <n-statistic :value="metrics?.yuanbot?.conversations?.total || 0" />
                </n-card>
              </n-gi>
              <n-gi>
                <n-card title="消息总数">
                  <n-statistic :value="metrics?.yuanbot?.conversations?.messages || 0" />
                </n-card>
              </n-gi>
              <n-gi>
                <n-card title="CPU">
                  <n-statistic :value="metrics?.system?.cpu_percent || 0" suffix="%" />
                </n-card>
              </n-gi>
            </n-grid>

            <n-grid :cols="2" :x-gap="16" style="margin-top: 16px">
              <n-gi>
                <n-card title="系统信息">
                  <n-descriptions :column="1" bordered>
                    <n-descriptions-item label="Python">
                      {{ metrics?.system?.python_version?.split(' ')[0] }}
                    </n-descriptions-item>
                    <n-descriptions-item label="内存">
                      {{ metrics?.system?.memory?.used_percent || 0 }}%
                    </n-descriptions-item>
                    <n-descriptions-item label="磁盘">
                      {{ metrics?.system?.disk?.used_percent || 0 }}%
                    </n-descriptions-item>
                  </n-descriptions>
                </n-card>
              </n-gi>
              <n-gi>
                <n-card title="系统维护">
                  <n-space vertical>
                    <n-button @click="handleBackup" block>📦 创建备份</n-button>
                    <n-button @click="loadData" block secondary>🔄 刷新数据</n-button>
                  </n-space>
                </n-card>
              </n-gi>
            </n-grid>
          </n-tab-pane>

          <!-- 用户管理 -->
          <n-tab-pane name="users" tab="用户管理">
            <n-space justify="end" style="margin-bottom: 16px">
              <n-button type="primary" @click="showCreateUser = true">+ 创建用户</n-button>
            </n-space>

            <n-data-table
              :columns="[
                { title: '用户名', key: 'username' },
                { title: '显示名', key: 'display_name' },
                { title: '角色', key: 'role' },
                { title: 'API Key', key: 'has_api_key', render: (row: any) => row.has_api_key ? '✅' : '❌' },
                {
                  title: '操作',
                  key: 'actions',
                  render: (row: any) => [
                    h('n-button', { text: true, size: 'small', onClick: () => handleGenerateApiKey(row.user_id) }, '生成Key'),
                    h('n-button', { text: true, size: 'small', type: 'error', onClick: () => handleDeleteUser(row.user_id, row.username) }, '删除'),
                  ],
                },
              ]"
              :data="users"
              :bordered="false"
            />
          </n-tab-pane>
        </n-tabs>

        <!-- 创建用户弹窗 -->
        <n-modal v-model:show="showCreateUser" preset="dialog" title="创建用户">
          <n-form label-placement="left" label-width="80">
            <n-form-item label="用户名">
              <n-input v-model:value="newUser.username" placeholder="username" />
            </n-form-item>
            <n-form-item label="密码">
              <n-input v-model:value="newUser.password" type="password" show-password-on="click" />
            </n-form-item>
            <n-form-item label="显示名">
              <n-input v-model:value="newUser.display_name" placeholder="可选" />
            </n-form-item>
            <n-form-item label="角色">
              <n-select
                v-model:value="newUser.role"
                :options="[{ label: '普通用户', value: 'user' }, { label: '管理员', value: 'admin' }]"
              />
            </n-form-item>
          </n-form>
          <template #action>
            <n-button @click="showCreateUser = false">取消</n-button>
            <n-button type="primary" @click="handleCreateUser">创建</n-button>
          </template>
        </n-modal>
      </template>
    </n-layout-content>
  </n-layout>
</template>

<script lang="ts">
import { h } from 'vue'
export default { name: 'AdminView' }
</script>
