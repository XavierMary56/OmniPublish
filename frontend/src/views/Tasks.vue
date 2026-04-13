<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/http'

const router = useRouter()
const activeFilter = ref('全部')
const filters = ['全部','进行中','待确认','切片中','已完成','失败']
const loading = ref(true)

const stepNames = ['文案','重命名','封面','水印','上传','发布']
const statusMap: Record<string, { label: string; badge: string }> = {
  running:           { label: '进行中', badge: 'badge-primary' },
  awaiting_confirm:  { label: '待确认', badge: 'badge-orange' },
  done:              { label: '已完成', badge: 'badge-green' },
  failed:            { label: '发布失败', badge: 'badge-red' },
  draft:             { label: '草稿', badge: 'badge-plain' },
}

interface TaskRow {
  id: number
  task_no: string
  title: string
  status: string
  current_step: number
  created_by: string
  created_at: string
  target_platforms: number[]
  platform_names: string[]
  steps: { step: number; status: string }[]
  platform_tasks: { platform_id: number; platform_name: string; wm_status: string; upload_status: string; publish_status: string; publish_error?: string }[]
}

const tasks = ref<TaskRow[]>([])
const expanded = ref<Set<number>>(new Set())

onMounted(async () => {
  await loadTasks()
})

async function loadTasks() {
  loading.value = true
  try {
    const data = await api('GET', '/tasks')
    tasks.value = data.items || data || []
  } catch (e) {
    console.error('加载任务失败', e)
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function toggleExpand(id: number) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

// 筛选
const filteredTasks = computed(() => {
  if (activeFilter.value === '全部') return tasks.value
  const filterMap: Record<string, string[]> = {
    '进行中': ['running'],
    '待确认': ['awaiting_confirm'],
    '切片中': ['running'], // 切片是 running 的子状态
    '已完成': ['done'],
    '失败': ['failed'],
  }
  const statuses = filterMap[activeFilter.value] || []
  return tasks.value.filter(t => statuses.includes(t.status))
})

// 统计
const miniStats = computed(() => [
  { label: '进行中', val: tasks.value.filter(t => t.status === 'running').length, cls: 'c-primary' },
  { label: '待确认', val: tasks.value.filter(t => t.status === 'awaiting_confirm').length, cls: 'c-orange' },
  { label: '已完成', val: tasks.value.filter(t => t.status === 'done').length, cls: 'c-green' },
  { label: '失败', val: tasks.value.filter(t => t.status === 'failed').length, cls: 'c-red' },
])

// 步骤状态映射
function stepClass(task: TaskRow, stepIdx: number): string {
  if (!task.steps?.length) {
    if (stepIdx < task.current_step) return 'done'
    if (stepIdx === task.current_step) return task.status === 'awaiting_confirm' ? 'hold' : 'run'
    return 'wait'
  }
  const s = task.steps.find(x => x.step === stepIdx)
  if (!s) return 'wait'
  if (s.status === 'done') return 'done'
  if (s.status === 'running') return 'run'
  if (s.status === 'awaiting_confirm') return 'hold'
  if (s.status === 'failed') return 'fail'
  return 'wait'
}

// 进度百分比
function progressPct(task: TaskRow): number {
  if (task.status === 'done') return 100
  const doneCount = task.steps?.filter(s => s.status === 'done').length || task.current_step
  return Math.round((doneCount / 6) * 100)
}

function progressColor(task: TaskRow): string {
  if (task.status === 'done') return 'var(--green)'
  if (task.status === 'failed') return 'var(--red)'
  if (task.status === 'awaiting_confirm') return 'var(--orange)'
  return 'var(--primary)'
}

// 状态显示
function statusInfo(task: TaskRow) {
  return statusMap[task.status] || { label: task.status, badge: 'badge-plain' }
}

// 操作按钮
function getAction(status: string) {
  if (status === 'awaiting_confirm') return { text: '处理', cls: 'action-orange' }
  if (status === 'failed') return { text: '重试', cls: 'action-red' }
  return { text: '详情', cls: 'btn-ghost' }
}

function handleAction(task: TaskRow) {
  router.push(`/pipeline/${task.id}`)
}

// 平台 badge 颜色轮转
const platformColors = ['badge-primary','badge-green','badge-orange','badge-purple','badge-pink','badge-cyan','badge-red']
function platformBadge(idx: number): string {
  return platformColors[idx % platformColors.length]
}

// 子任务状态
function subStatusBadge(sub: any) {
  if (sub.publish_status === 'done') return { cls: 'badge-green', text: '已发布' }
  if (sub.publish_status === 'failed') return { cls: 'badge-red', text: '发布失败' }
  if (sub.upload_status === 'running') return { cls: 'badge-primary', text: '上传中' }
  if (sub.upload_status === 'done') return { cls: 'badge-orange', text: '待发布' }
  if (sub.wm_status === 'done') return { cls: 'badge-primary', text: '水印完成' }
  if (sub.wm_status === 'running') return { cls: 'badge-primary', text: '水印中' }
  return { cls: 'badge-plain', text: '待处理' }
}

// 格式化时间
function formatTime(dt: string): string {
  if (!dt) return ''
  const d = new Date(dt)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`
}
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">任务看板</div>
    <div class="filter-row">
      <button v-for="f in filters" :key="f" class="filter-btn" :class="{active: activeFilter===f}" @click="activeFilter=f">{{ f }}</button>
    </div>
  </div>

  <!-- Mini Stats -->
  <div class="stats-row" style="margin-bottom:16px">
    <div v-for="s in miniStats" :key="s.label" class="stat-card" :class="s.cls" style="padding:12px 16px">
      <div class="stat-label">{{ s.label }}</div>
      <div class="stat-value" style="font-size:22px">{{ s.val }}</div>
    </div>
  </div>

  <!-- Loading -->
  <div v-if="loading" style="text-align:center;padding:40px;color:var(--t3)">加载中...</div>

  <!-- Empty -->
  <div v-else-if="!filteredTasks.length" style="text-align:center;padding:40px;color:var(--t3)">
    {{ tasks.length ? '没有符合筛选条件的任务' : '暂无任务，去创建一个吧' }}
  </div>

  <!-- Task Table -->
  <div v-else class="table-wrap">
    <table>
      <thead><tr>
        <th style="width:30px"></th>
        <th>ID</th>
        <th>任务编号</th>
        <th>标题</th>
        <th>目标平台</th>
        <th>流水线进度</th>
        <th>状态</th>
        <th>编辑</th>
        <th>创建时间</th>
        <th>操作</th>
      </tr></thead>
      <tbody>
        <template v-for="t in filteredTasks" :key="t.id">
          <tr style="cursor:pointer" @click="toggleExpand(t.id)">
            <td style="color:var(--t3);font-size:14px">{{ expanded.has(t.id) ? '▼' : '▶' }}</td>
            <td class="t1" style="color:var(--t3);font-size:11px">{{ t.id }}</td>
            <td class="t1">{{ t.task_no }}</td>
            <td class="t1">{{ t.title || '(未设标题)' }}</td>
            <td>
              <div style="display:flex;gap:3px;flex-wrap:wrap">
                <template v-if="t.platform_tasks?.length">
                  <span v-for="(pt, i) in t.platform_tasks.slice(0, 4)" :key="pt.platform_id"
                        class="badge" :class="platformBadge(i)" style="font-size:10px;padding:1px 6px">
                    {{ pt.platform_name }}
                  </span>
                  <span v-if="t.platform_tasks.length > 4" class="badge badge-plain" style="font-size:10px;padding:1px 6px">
                    +{{ t.platform_tasks.length - 4 }}
                  </span>
                </template>
                <span v-else style="font-size:11px;color:var(--t3)">—</span>
              </div>
            </td>
            <td>
              <div class="steps-row">
                <span v-for="(name, i) in stepNames" :key="i" class="step-pill" :class="stepClass(t, i)">{{ name }}</span>
              </div>
              <div class="progress-bar"><div class="progress-fill" :style="{width:progressPct(t)+'%',background:progressColor(t)}" /></div>
            </td>
            <td><span class="badge" :class="statusInfo(t).badge">{{ statusInfo(t).label }}</span></td>
            <td>{{ t.created_by || '—' }}</td>
            <td style="white-space:nowrap">{{ formatTime(t.created_at) }}</td>
            <td>
              <button class="btn btn-sm" :class="getAction(t.status).cls" @click.stop="handleAction(t)">
                {{ getAction(t.status).text }}
              </button>
            </td>
          </tr>
          <!-- 展开：平台分发状态 -->
          <tr v-if="expanded.has(t.id) && t.platform_tasks?.length" class="expand-row">
            <td colspan="10" style="padding:0;background:var(--bg1)">
              <div style="padding:8px 14px 4px 44px;font-size:11px;color:var(--t3);font-weight:600">各平台分发状态</div>
              <div v-for="(sub, i) in t.platform_tasks" :key="sub.platform_id" class="sub-task-row">
                <span class="badge" :class="platformBadge(i)" style="font-size:10px;padding:1px 6px;min-width:70px;justify-content:center">
                  {{ sub.platform_name }}
                </span>
                <div style="display:flex;gap:8px;align-items:center;font-size:11px">
                  <span class="step-pill" :class="sub.wm_status === 'done' ? 'done' : sub.wm_status === 'running' ? 'run' : 'wait'">水印</span>
                  <span class="step-pill" :class="sub.upload_status === 'done' ? 'done' : sub.upload_status === 'running' ? 'run' : 'wait'">上传</span>
                  <span class="step-pill" :class="sub.publish_status === 'done' ? 'done' : sub.publish_status === 'failed' ? 'fail' : 'wait'">发布</span>
                </div>
                <span class="badge" :class="subStatusBadge(sub).cls" style="font-size:10px">{{ subStatusBadge(sub).text }}</span>
                <span v-if="sub.publish_error" style="font-size:10px;color:var(--red);margin-left:auto">{{ sub.publish_error }}</span>
              </div>
            </td>
          </tr>
          <tr v-if="expanded.has(t.id) && !t.platform_tasks?.length" class="expand-row">
            <td colspan="10" style="padding:12px 44px;background:var(--bg1);font-size:12px;color:var(--t3)">
              此任务暂无平台级分发详情
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</div>
</template>

<style scoped>
.sub-task-row{display:flex;align-items:center;gap:14px;padding:8px 14px 8px 44px;border-bottom:1px solid rgba(42,42,58,.5);font-size:12px}
.sub-task-row:last-child{border-bottom:none}
.expand-row td{border-bottom:none}
.action-orange{color:var(--orange)!important;border:1px solid var(--orange)!important;background:transparent!important}
.action-red{color:var(--red)!important;border:1px solid var(--red)!important;background:transparent!important}
</style>
