<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(false)
const loginMode = ref<'password' | 'apikey'>('password')

const form = ref({
  username: '',
  password: '',
  apiKey: '',
})

async function handleLogin() {
  loading.value = true
  try {
    if (loginMode.value === 'password') {
      await auth.login(form.value.username, form.value.password)
    } else {
      await auth.loginWithApiKey(form.value.apiKey)
    }
    message.success('登录成功')
    router.push('/')
  } catch (e: any) {
    message.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <n-card class="login-card" title="🌸 缘·Bot">
      <template #header-extra>
        <n-text depth="3">AI 虚拟伴侣系统</n-text>
      </template>

      <n-tabs v-model:value="loginMode" type="segment" animated>
        <n-tab-pane name="password" tab="用户名登录">
          <n-form :model="form" label-placement="left">
            <n-form-item label="用户名" path="username">
              <n-input v-model:value="form.username" placeholder="请输入用户名" @keyup.enter="handleLogin" />
            </n-form-item>
            <n-form-item label="密码" path="password">
              <n-input
                v-model:value="form.password"
                type="password"
                show-password-on="click"
                placeholder="请输入密码"
                @keyup.enter="handleLogin"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="apikey" tab="API Key 登录">
          <n-form label-placement="left">
            <n-form-item label="API Key">
              <n-input v-model:value="form.apiKey" placeholder="yuan_xxx..." @keyup.enter="handleLogin" />
            </n-form-item>
          </n-form>
        </n-tab-pane>
      </n-tabs>

      <n-button
        type="primary"
        block
        :loading="loading"
        @click="handleLogin"
        style="margin-top: 16px"
      >
        登录
      </n-button>
    </n-card>
  </div>
</template>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 16px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
</style>
