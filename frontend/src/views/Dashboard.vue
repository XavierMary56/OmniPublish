<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/http'

const router = useRouter()
const stats = ref({ total: 0, done: 0, running: 0, failed: 0, platforms: 0, success_rate: 0, awaiting_confirm: 0, yesterday_total: 0 })
const recentTasks = ref<any[]>([])
const barData = ref<any[]>([])
const pendingItems = ref<any[]>([])

const stepNames = ['文案','重命名','封面','水印','上传','发布']
const badgeColors = ['badge-primary','badge-green','badge-orange','badge-purple','badge-pink','badge-cyan','badge-red']
const barColors = ['var(--primary)','var(--green)','var(--orange)','var(--purple)','var(--pink)','var(--cyan)','var(--red)']

const statusMap: Record<string, { label: string; badge: string }> = {
  draft:             { label: '草稿',   badge: 'badge-plain' },
  running:           { label: '进行中', badge: 'badge-primary' },
  slicing:           { label: '切片中', badge: 'badge-orange' },
  awaiting_confirm:  { label: '待确认', badge: 'badge-orange' },
  done:              { label: '已完成', badge: 'badge-green' },
  failed:            { label: '失败',   badge: 'badge-red' },
  partial:           { label: '部分失败', badge: 'badge-red' },
}

/* Map raw task to display row */
function mapTask(t: any) {
  const id = '#' + String(t.task_no || t.id).padStart(4, '0')
  const title = (t.title || '').length > 16 ? t.title.slice(0, 16) + '…' : (t.title || '')

  // Platform badges
  const ptNames: string[] = (t.platform_tasks || []).map((pt: any) => pt.platform_name)
  const shown = ptNames.slice(0, 2).map((n: string, i: number) => ({ n, c: badgeColors[i % badgeColors.length] }))
  if (ptNames.length > 2) shown.push({ n: '+' + (ptNames.length - 2), c: 'badge-plain' })

  // Steps
  const stepStatuses: string[] = []
  if (t.steps && t.steps.length) {
    for (let i = 0; i < 6; i++) {
      const s = t.steps.find((st: any) => st.step === i)
      if (!s) { stepStatuses.push('wait'); continue }
      if (s.status === 'done') stepStatuses.push('done')
      else if (s.status === 'running') stepStatuses.push('run')
      else if (s.status === 'awaiting_confirm') stepStatuses.push('hold')
      else stepStatuses.push('wait')
    }
  } else {
    const cur = t.current_step || 0
    for (let i = 0; i < 6; i++) {
      if (i < cur) stepStatuses.push('done')
      else if (i === cur && t.status === 'running') stepStatuses.push('run')
      else stepStatuses.push('wait')
    }
  }

  // Progress
  const doneSteps = stepStatuses.filter(s => s === 'done').length
  const pct = t.status === 'done' ? 100 : Math.round((doneSteps / 6) * 100)
  const pColor = t.status === 'done' ? 'var(--green)' : t.status === 'failed' ? 'var(--red)' : 'var(--primary)'

  const sm = statusMap[t.status] || { label: t.status, badge: 'badge-plain' }
  const time = (t.created_at || '').slice(0, 16).replace('T', ' ')

  return { id, title, platforms: shown, steps: stepStatuses, pct, pColor, st: sm.label, sc: sm.badge, time }
}

/* Map pending task to display item */
function mapPending(t: any) {
  const id = '#' + String(t.task_no || t.id).padStart(4, '0')
  const holdStep = (t.steps || []).find((s: any) => s.status === 'awaiting_confirm')
  const stepIdx = holdStep ? holdStep.step : (t.current_step || 0)
  const label = (stepNames[stepIdx] || '步骤') + '待确认'
  const desc = (t.title || '').length > 20 ? t.title.slice(0, 20) + '…' : (t.title || '')
  return { id, label, desc, st: '待确认', sc: 'badge-orange' }
}

/* Diff text for stats sub */
const diffText = computed(() => {
  const diff = stats.value.total - stats.value.yesterday_total
  if (diff > 0) return `较昨日 ↑ ${diff}`
  if (diff < 0) return `较昨日 ↓ ${Math.abs(diff)}`
  return '与昨日持平'
})

onMounted(async () => {
  // Fire all API calls in parallel
  const [overviewRes, platformsRes, tasksRes, pendingRes] = await Promise.allSettled([
    api('GET', '/stats/overview', { period: 'today' }),
    api('GET', '/stats/platforms', { period: 'today' }),
    api('GET', '/tasks', { page: 1, limit: 5 }),
    api('GET', '/tasks', { status: 'awaiting_confirm', page: 1, limit: 5 }),
  ])

  // Stats overview
  if (overviewRes.status === 'fulfilled' && overviewRes.value) {
    stats.value = { ...stats.value, ...overviewRes.value }
  }

  // Bar chart from platforms
  if (platformsRes.status === 'fulfilled' && Array.isArray(platformsRes.value)) {
    const platforms = platformsRes.value as any[]
    const maxVal = Math.max(...platforms.map(p => p.total), 1)
    barData.value = platforms.slice(0, 7).map((p, i) => ({
      label: p.name,
      val: p.total,
      pct: Math.round((p.total / maxVal) * 100),
      color: barColors[i % barColors.length],
    }))
  }

  // Recent tasks
  if (tasksRes.status === 'fulfilled' && tasksRes.value?.items) {
    recentTasks.value = tasksRes.value.items.map(mapTask)
  }

  // Pending items
  if (pendingRes.status === 'fulfilled' && pendingRes.value?.items) {
    pendingItems.value = pendingRes.value.items.map(mapPending)
  }
})
</script>

<template>
<div>
  <div class="proto-banner">💡 OmniPublish V2.0 全链路发帖工作台 · 自动化流水线 + 多平台分发 + 任务追踪</div>

  <!-- Stats -->
  <div class="stats-row">
    <div class="stat-card c-primary"><div class="stat-label">今日发帖</div><div class="stat-value">{{ stats.total }}</div><div class="stat-sub">{{ diffText }}</div></div>
    <div class="stat-card c-green"><div class="stat-label">已完成</div><div class="stat-value">{{ stats.done }}</div><div class="stat-sub">成功率 {{ stats.success_rate }}%</div></div>
    <div class="stat-card c-orange"><div class="stat-label">流水线进行中</div><div class="stat-value">{{ stats.running }}</div><div class="stat-sub">{{ stats.awaiting_confirm }} 个待人工确认</div></div>
    <div class="stat-card c-red"><div class="stat-label">发布失败</div><div class="stat-value">{{ stats.failed }}</div><div class="stat-sub">点击查看详情</div></div>
    <div class="stat-card c-purple"><div class="stat-label">覆盖平台</div><div class="stat-value">{{ stats.platforms }}</div><div class="stat-sub">今日活跃 {{ stats.platforms }} 个</div></div>
  </div>

  <div style="display:flex;gap:16px;flex-wrap:wrap">
    <!-- Left: Recent Tasks Table -->
    <div style="flex:2;min-width:500px">
      <div class="section-header">
        <div class="section-title">最近流水线任务</div>
        <button class="btn btn-ghost btn-sm" @click="router.push('/tasks')">查看全部 →</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>标题</th><th>目标平台</th><th>流水线进度</th><th>状态</th><th>时间</th></tr></thead>
          <tbody>
            <tr v-for="t in recentTasks" :key="t.id">
              <td class="t1">{{ t.id }}</td>
              <td class="t1">{{ t.title }}</td>
              <td><div style="display:flex;gap:3px;flex-wrap:wrap"><span v-for="p in t.platforms" :key="p.n" class="badge" :class="p.c" style="font-size:10px;padding:1px 6px">{{ p.n }}</span></div></td>
              <td>
                <div class="steps-row"><span v-for="(s,i) in t.steps" :key="i" class="step-pill" :class="s">{{ stepNames[i] }}</span></div>
                <div class="progress-bar"><div class="progress-fill" :style="{width:t.pct+'%',background:t.pColor}" /></div>
              </td>
              <td><span class="badge" :class="t.sc">{{ t.st }}</span></td>
              <td style="white-space:nowrap">{{ t.time }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Right: Chart + Pending -->
    <div style="flex:1;min-width:280px">
      <div class="section-header"><div class="section-title">今日各平台发帖</div></div>
      <div class="panel" style="margin:0">
        <div class="bar-chart" style="height:180px">
          <div v-for="b in barData" :key="b.label" class="bar-col">
            <div class="bar-val">{{ b.val }}</div>
            <div class="bar" :style="{height:b.pct+'%',background:b.color}" />
            <div class="bar-label">{{ b.label }}</div>
          </div>
        </div>
      </div>

      <div style="margin-top:16px">
        <div style="font-size:14px;font-weight:700;margin-bottom:10px">待我处理 <span style="font-size:11px;color:var(--t3);font-weight:400">（仅显示我的任务）</span></div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div v-for="item in pendingItems" :key="item.id" class="pending-card" @click="router.push('/tasks')">
            <div><div style="font-size:12px;font-weight:600;color:var(--t1)">{{ item.id }} {{ item.label }}</div><div style="font-size:11px;color:var(--t3);margin-top:2px">{{ item.desc }}</div></div>
            <span class="badge" :class="item.sc" style="font-size:10px">{{ item.st }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.proto-banner{background:linear-gradient(90deg,rgba(79,195,247,.08),rgba(179,157,219,.08));border:1px solid rgba(79,195,247,.2);border-radius:8px;padding:10px 16px;margin-bottom:20px;font-size:12px;color:var(--primary);display:flex;align-items:center;gap:8px}
.bar-chart{display:flex;align-items:flex-end;gap:6px;padding:0 10px}
.bar-col{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}
.bar-col .bar{width:100%;min-width:20px;border-radius:4px 4px 0 0;transition:.3s}
.bar-col .bar-label{font-size:9px;color:var(--t3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60px}
.bar-col .bar-val{font-size:10px;color:var(--t2);font-weight:600}
.pending-card{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--bg2);border:1px solid var(--bd);border-radius:8px;cursor:pointer;transition:.15s}
.pending-card:hover{border-color:var(--primary)}
</style>
