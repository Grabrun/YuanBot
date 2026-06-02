import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('./views/LoginView.vue'),
    },
    {
      path: '/',
      name: 'chat',
      component: () => import('./views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('./views/AdminView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/providers',
      name: 'providers',
      component: () => import('./views/ProviderView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/memory',
      name: 'memory',
      component: () => import('./views/MemoryView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/plugins',
      name: 'plugins',
      component: () => import('./views/PluginView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/marketplace',
      name: 'marketplace',
      component: () => import('./views/MarketplaceView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('./views/LogView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('./views/ConfigView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/personas',
      name: 'personas',
      component: () => import('./views/PersonaStoreView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const token = api.getToken()
  if (to.meta.requiresAuth && !token) {
    return { name: 'login' }
  }
  if (to.name === 'login' && token) {
    return { name: 'chat' }
  }
})

export default router
