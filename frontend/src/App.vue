<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { notificationWs } from './api/ws'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isLoginPage = computed(() => route.name === 'login')

const navItems = [
  { section: '核心', items: [
    { name: 'dashboard', label: '工作台', icon: '📊' },
    { name: 'pipeline', label: '新建发帖任务', icon: '🚀', badge: 'New' },
    { name: 'tasks', label: '任务看板', icon: '📋' },
  ]},
  { section: '数据', items: [
    { name: 'analytics', label: '数据统计', icon: '📈' },
  ]},
  { section: '工具', items: [
    { name: 'toolbox', label: '工具箱', icon: '🧰' },
  ]},
  { section: '管理', items: [
    { name: 'platforms', label: '业务线管理', icon: '⚙️', admin: true },
    { name: 'accounts', label: '账号管理', icon: '🔑', admin: true },
  ]},
]

const pageTitle = computed(() => {
  const map: Record<string, string> = {
    dashboard: '工作台', pipeline: '新建发帖任务', 'pipeline-detail': '发帖任务详情', tasks: '任务看板',
    analytics: '数据统计', toolbox: '工具箱', platforms: '业务线管理', accounts: '账号管理',
  }
  return map[route.name as string] || 'OmniPublish'
})

function navigate(name: string) { router.push({ name }) }

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  if (auth.token) {
    await auth.fetchMe()
    notificationWs.connect()
  }
})
</script>

<template>
  <!-- Login page: no layout -->
  <router-view v-if="isLoginPage" />

  <!-- App layout -->
  <div v-else style="display:flex;min-height:100vh">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <div style="font-size:17px;font-weight:800;color:var(--primary)">OmniPublish</div>
        <div style="font-size:11px;color:var(--t3);margin-top:2px">V2.0 · 全链路发帖工作台</div>
      </div>

      <template v-for="group in navItems" :key="group.section">
        <div class="nav-section">{{ group.section }}</div>
        <template v-for="item in group.items" :key="item.name">
          <div v-if="!item.admin || auth.isAdmin"
               class="nav-item" :class="{ active: route.name === item.name || (item.name === 'pipeline' && route.name === 'pipeline-detail') }"
               @click="navigate(item.name)">
            <span class="nav-icon">{{ item.icon }}</span>
            {{ item.label }}
            <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
          </div>
        </template>
      </template>

      <div style="flex:1" />
      <div class="sidebar-footer">
        <div>服务状态：<span style="color:var(--green)">● 在线</span></div>
        <div style="margin-top:4px">👤 {{ auth.user?.display_name || '—' }} · {{ auth.user?.dept || '' }}</div>
        <div style="margin-top:2px;color:var(--t3);cursor:pointer" @click="logout">退出登录</div>
      </div>
    </aside>

    <!-- Main -->
    <div class="main-content">
      <div class="topbar">
        <span style="font-size:16px;font-weight:700">{{ pageTitle }}</span>
        <div style="display:flex;align-items:center;gap:14px">
          <span style="font-size:12px;color:var(--t2)">👤 {{ auth.user?.display_name || '' }}</span>
          <button class="btn btn-primary" @click="navigate('pipeline')">＋ 新建发帖任务</button>
        </div>
      </div>
      <div class="page-container">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-w); background: var(--bg1); border-right: 1px solid var(--bd);
  display: flex; flex-direction: column; position: fixed; top: 0; left: 0; bottom: 0; z-index: 100; overflow-y: auto;
}
.sidebar-logo { padding: 20px 18px 16px; border-bottom: 1px solid var(--bd); }
.nav-section { padding: 14px 0 6px 18px; font-size: 10px; color: var(--t3); text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600; }
.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 9px 18px; cursor: pointer;
  color: var(--t2); font-size: 13px; border-left: 3px solid transparent; transition: .15s; position: relative;
}
.nav-item:hover { background: var(--bg3); color: var(--t1); }
.nav-item.active { color: var(--primary); border-left-color: var(--primary); background: var(--primary-dim); }
.nav-icon { width: 20px; text-align: center; font-size: 15px; flex-shrink: 0; }
.nav-badge { position: absolute; right: 14px; background: var(--red); color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 10px; font-weight: 600; }
.sidebar-footer { padding: 14px 18px; border-top: 1px solid var(--bd); font-size: 11px; color: var(--t3); }

.main-content { margin-left: var(--sidebar-w); flex: 1; display: flex; flex-direction: column; min-height: 100vh; }
.topbar {
  height: 54px; background: var(--bg1); border-bottom: 1px solid var(--bd);
  display: flex; align-items: center; justify-content: space-between; padding: 0 28px; flex-shrink: 0;
}
.page-container { padding: 24px 28px 40px; flex: 1; overflow-y: auto; }
</style>
