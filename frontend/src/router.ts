import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
    { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
    { path: '/pipeline', name: 'pipeline', component: () => import('./views/Pipeline.vue') },
    { path: '/pipeline/:id', name: 'pipeline-detail', component: () => import('./views/Pipeline.vue'), props: true },
    { path: '/tasks', name: 'tasks', component: () => import('./views/Tasks.vue') },
    { path: '/analytics', name: 'analytics', component: () => import('./views/Analytics.vue') },
    { path: '/toolbox', name: 'toolbox', component: () => import('./views/Toolbox.vue') },
    { path: '/platforms', name: 'platforms', component: () => import('./views/Platforms.vue') },
    { path: '/accounts', name: 'accounts', component: () => import('./views/Accounts.vue') },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) {
    return { name: 'login' }
  }
})

export default router
