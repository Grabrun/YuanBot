import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, type User } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function checkAuth() {
    const token = api.getToken()
    if (!token) {
      user.value = null
      return false
    }
    try {
      user.value = await api.getMe()
      return true
    } catch {
      api.clearToken()
      user.value = null
      return false
    }
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const resp = await api.login(username, password)
      user.value = resp.user
      return true
    } catch (e) {
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loginWithApiKey(apiKey: string) {
    loading.value = true
    try {
      const resp = await api.loginWithApiKey(apiKey)
      user.value = resp.user
      return true
    } catch (e) {
      throw e
    } finally {
      loading.value = false
    }
  }

  function logout() {
    api.logout()
    user.value = null
  }

  return { user, loading, isAuthenticated, isAdmin, checkAuth, login, loginWithApiKey, logout }
})
