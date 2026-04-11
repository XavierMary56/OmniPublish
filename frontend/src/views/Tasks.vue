<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const activeFilter = ref('全部')
const filters = ['全部','进行中','待确认','切片中','已完成','失败']

const stepNames = ['文案','重命名','封面','水印','上传','发布']

// 子任务的独立状态
const tasks = ref([
  { id:'#0052', taskId: 52, title:'极品女神私密视频流出…',
    platforms:[{n:'91视频',c:'badge-primary'},{n:'海角社区',c:'badge-green'},{n:'黑料情报',c:'badge-orange'},{n:'91porn',c:'badge-purple'},{n:'糖心',c:'badge-pink'}],
    steps:['done','done','run','wait','wait','wait'], pct:40, pColor:'var(--primary)', st:'进行中', sc:'badge-primary', editor:'张伟', time:'2026-04-11 10:42',
    subs:[
      {n:'91视频',c:'badge-primary', wmStatus:'pending', uploadStatus:'pending', publishStatus:'pending', statusText:'待水印处理'},
      {n:'海角社区',c:'badge-green', wmStatus:'pending', uploadStatus:'pending', publishStatus:'pending', statusText:'待水印处理'},
      {n:'黑料情报',c:'badge-orange', wmStatus:'pending', uploadStatus:'pending', publishStatus:'pending', statusText:'待水印处理'},
      {n:'91porn',c:'badge-purple', wmStatus:'pending', uploadStatus:'pending', publishStatus:'pending', statusText:'待水印处理'},
      {n:'糖心',c:'badge-pink', wmStatus:'pending', uploadStatus:'pending', publishStatus:'pending', statusText:'待水印处理'},
    ]
  },
  { id:'#0051', taskId: 51, title:'大学生情侣出租屋偷拍…',
    platforms:[{n:'黑料情报局',c:'badge-orange'},{n:'91porn',c:'badge-purple'}],
    steps:['done','done','done','done','run','wait'], pct:78, pColor:'var(--primary)', st:'切片中', sc:'badge-orange', editor:'张伟', time:'2026-04-11 10:28',
    subs:[
      {n:'黑料情报局',c:'badge-orange', wmStatus:'done', uploadStatus:'running', publishStatus:'pending', statusText:'上传中 78%'},
      {n:'91porn',c:'badge-purple', wmStatus:'done', uploadStatus:'pending', publishStatus:'pending', statusText:'排队等待'},
    ]
  },
  { id:'#0050', taskId: 50, title:'网红主播浴室大尺度直播…',
    platforms:[{n:'糖心',c:'badge-pink'},{n:'9色视频',c:'badge-cyan'},{n:'+5',c:'badge-plain'}],
    steps:['done','done','done','done','done','done'], pct:100, pColor:'var(--green)', st:'已完成', sc:'badge-green', editor:'李梦', time:'2026-04-11 10:05',
    subs:[]
  },
  { id:'#0049', taskId: 49, title:'某高校教授丑闻曝光…',
    platforms:[{n:'18黑料',c:'badge-red'},{n:'黑料吃瓜',c:'badge-orange'}],
    steps:['done','done','hold','wait','wait','wait'], pct:35, pColor:'var(--orange)', st:'待确认', sc:'badge-orange', editor:'王超', time:'2026-04-10 09:51',
    subs:[]
  },
  { id:'#0048', taskId: 48, title:'健身教练与学员私下…',
    platforms:[{n:'91视频',c:'badge-primary'},{n:'91hub',c:'badge-cyan'}],
    steps:['done','done','done','done','done','fail'], pct:90, pColor:'var(--red)', st:'发布失败', sc:'badge-red', editor:'陈晓', time:'2026-04-10 09:33',
    subs:[
      {n:'91视频',c:'badge-primary', wmStatus:'done', uploadStatus:'done', publishStatus:'done', statusText:'已发布'},
      {n:'91hub',c:'badge-cyan', wmStatus:'done', uploadStatus:'done', publishStatus:'failed', statusText:'发布失败: API 超时'},
    ]
  },
])

const expanded = ref<Set<string>>(new Set())
function toggleExpand(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

const filteredTasks = computed(() => {
  if (activeFilter.value === '全部') return tasks.value
  return tasks.value.filter(t => t.st === activeFilter.value)
})

function setFilter(f: string) {
  activeFilter.value = f
}

// 动态统计
const miniStats = computed(() => [
  { label: '进行中', val: tasks.value.filter(t => t.st === '进行中').length, cls: 'c-primary' },
  { label: '待确认', val: tasks.value.filter(t => t.st === '待确认').length, cls: 'c-orange' },
  { label: '今日完成', val: tasks.value.filter(t => t.st === '已完成').length, cls: 'c-green' },
  { label: '失败', val: tasks.value.filter(t => t.st === '发布失败').length, cls: 'c-red' },
])

// 操作按钮文字和样式
function getAction(st: string) {
  switch(st) {
    case '待确认': return { text: '处理', cls: 'action-orange' }
    case '发布失败': return { text: '重试', cls: 'action-red' }
    default: return { text: '详情', cls: 'btn-ghost' }
  }
}

// 点击操作按钮
function handleAction(task: any) {
  router.push(`/pipeline/${task.taskId}`)
}

// 子任务状态 badge
function subStatusBadge(sub: any) {
  if (sub.publishStatus === 'done') return { cls: 'badge-green', text: '已发布' }
  if (sub.publishStatus === 'failed') return { cls: 'badge-red', text: '发布失败' }
  if (sub.uploadStatus === 'running') return { cls: 'badge-primary', text: '上传中' }
  if (sub.uploadStatus === 'done') return { cls: 'badge-orange', text: '待发布' }
  if (sub.wmStatus === 'done') return { cls: 'badge-primary', text: '水印完成' }
  if (sub.wmStatus === 'running') return { cls: 'badge-primary', text: '水印处理中' }
  return { cls: 'badge-plain', text: sub.statusText || '待处理' }
}
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">任务看板</div>
    <div class="filter-row">
      <button v-for="f in filters" :key="f" class="filter-btn" :class="{active: activeFilter===f}" @click="setFilter(f)">{{ f }}</button>
    </div>
  </div>

  <!-- Mini Stats -->
  <div class="stats-row" style="margin-bottom:16px">
    <div v-for="s in miniStats" :key="s.label" class="stat-card" :class="s.cls" style="padding:12px 16px">
      <div class="stat-label">{{ s.label }}</div>
      <div class="stat-value" style="font-size:22px">{{ s.val }}</div>
    </div>
  </div>

  <!-- Task Table -->
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th style="width:30px"></th><th>任务 ID</th><th>标题</th><th>目标平台</th><th>流水线进度</th><th>状态</th><th>编辑</th><th>创建时间</th><th>操作</th>
      </tr></thead>
      <tbody>
        <template v-for="t in filteredTasks" :key="t.id">
          <!-- Main row -->
          <tr style="cursor:pointer" @click="toggleExpand(t.id)">
            <td style="color:var(--t3);font-size:14px">{{ expanded.has(t.id) ? '▼' : '▶' }}</td>
            <td class="t1">{{ t.id }}</td>
            <td class="t1">{{ t.title }}</td>
            <td>
              <div style="display:flex;gap:3px;flex-wrap:wrap">
                <span v-for="p in t.platforms" :key="p.n" class="badge" :class="p.c" style="font-size:10px;padding:1px 6px">{{ p.n }}</span>
              </div>
            </td>
            <td>
              <div class="steps-row"><span v-for="(s,i) in t.steps" :key="i" class="step-pill" :class="s">{{ stepNames[i] }}</span></div>
              <div class="progress-bar"><div class="progress-fill" :style="{width:t.pct+'%',background:t.pColor}" /></div>
            </td>
            <td><span class="badge" :class="t.sc">{{ t.st }}</span></td>
            <td>{{ t.editor }}</td>
            <td style="white-space:nowrap">{{ t.time }}</td>
            <td>
              <button class="btn btn-sm" :class="getAction(t.st).cls" @click.stop="handleAction(t)">
                {{ getAction(t.st).text }}
              </button>
            </td>
          </tr>
          <!-- Expanded sub-tasks: 只显示 Step 5-6 的独立平台状态 -->
          <tr v-if="expanded.has(t.id) && t.subs.length" class="expand-row">
            <td colspan="9" style="padding:0;background:var(--bg1)">
              <div style="padding:8px 14px 4px 44px;font-size:11px;color:var(--t3);font-weight:600">各平台分发状态</div>
              <div v-for="sub in t.subs" :key="sub.n" class="sub-task-row">
                <span class="badge" :class="sub.c" style="font-size:10px;padding:1px 6px;min-width:70px;justify-content:center">{{ sub.n }}</span>
                <!-- 只显示水印和上传/发布的独立状态 -->
                <div style="display:flex;gap:8px;align-items:center;font-size:11px">
                  <span class="step-pill" :class="sub.wmStatus === 'done' ? 'done' : sub.wmStatus === 'running' ? 'run' : 'wait'">水印</span>
                  <span class="step-pill" :class="sub.uploadStatus === 'done' ? 'done' : sub.uploadStatus === 'running' ? 'run' : 'wait'">上传</span>
                  <span class="step-pill" :class="sub.publishStatus === 'done' ? 'done' : sub.publishStatus === 'failed' ? 'fail' : 'wait'">发布</span>
                </div>
                <span class="badge" :class="subStatusBadge(sub).cls" style="font-size:10px">{{ subStatusBadge(sub).text }}</span>
              </div>
            </td>
          </tr>
          <!-- 没有子任务时也可展开看共享步骤 -->
          <tr v-if="expanded.has(t.id) && !t.subs.length" class="expand-row">
            <td colspan="9" style="padding:12px 44px;background:var(--bg1);font-size:12px;color:var(--t3)">
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
