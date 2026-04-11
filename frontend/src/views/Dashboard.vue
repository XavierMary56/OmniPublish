<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/http'

const router = useRouter()
const stats = ref({ total: 47, done: 38, running: 6, failed: 3, platforms: 35 })

const recentTasks = ref([
  { id:'#0052', title:'极品女神私密视频流出…', platforms:[{n:'91视频',c:'badge-primary'},{n:'海角社区',c:'badge-green'},{n:'+3',c:'badge-plain'}], steps:['done','done','run','wait','wait','wait'], pct:40, pColor:'var(--primary)', st:'进行中', sc:'badge-primary', time:'2026-04-11 10:42' },
  { id:'#0051', title:'大学生情侣出租屋偷拍…', platforms:[{n:'黑料情报局',c:'badge-orange'},{n:'91porn',c:'badge-purple'}], steps:['done','done','done','done','run','wait'], pct:78, pColor:'var(--primary)', st:'切片中', sc:'badge-orange', time:'2026-04-11 10:28' },
  { id:'#0050', title:'网红主播浴室大尺度直播…', platforms:[{n:'糖心',c:'badge-pink'},{n:'9色视频',c:'badge-cyan'},{n:'+5',c:'badge-plain'}], steps:['done','done','done','done','done','done'], pct:100, pColor:'var(--green)', st:'已完成', sc:'badge-green', time:'2026-04-11 10:05' },
  { id:'#0049', title:'某高校教授丑闻曝光…', platforms:[{n:'18黑料',c:'badge-red'},{n:'黑料吃瓜',c:'badge-orange'}], steps:['done','done','hold','wait','wait','wait'], pct:35, pColor:'var(--orange)', st:'待确认', sc:'badge-orange', time:'2026-04-11 09:51' },
])

const barData = [
  { label:'91视频', val:12, pct:85, color:'var(--primary)' },
  { label:'海角社区', val:9, pct:64, color:'var(--green)' },
  { label:'黑料情报', val:7, pct:50, color:'var(--orange)' },
  { label:'91porn', val:6, pct:43, color:'var(--purple)' },
  { label:'糖心', val:5, pct:36, color:'var(--pink)' },
  { label:'9色视频', val:4, pct:28, color:'var(--cyan)' },
  { label:'其他', val:4, pct:28, color:'var(--red)' },
]

const pendingItems = [
  { id:'#0052', label:'封面待确认', desc:'3 张候选封面等待选择', st:'待确认', sc:'badge-orange' },
  { id:'#0049', label:'封面不满意', desc:'需要手动重新选图生成', st:'需处理', sc:'badge-red' },
  { id:'#0051', label:'等待视频切片', desc:'预计还需 3 分钟', st:'等待中', sc:'badge-primary' },
]

const stepNames = ['文案','重命名','封面','水印','上传','发布']

onMounted(async () => {
  try {
    const d = await api('GET', '/stats/overview', { period: 'today' })
    if (d) { stats.value = { ...stats.value, ...d } }
  } catch {}
})
</script>

<template>
<div>
  <div class="proto-banner">💡 OmniPublish V2.0 全链路发帖工作台 · 自动化流水线 + 多平台分发 + 任务追踪</div>

  <!-- Stats -->
  <div class="stats-row">
    <div class="stat-card c-primary"><div class="stat-label">今日发帖</div><div class="stat-value">{{ stats.total }}</div><div class="stat-sub">较昨日 ↑ 8</div></div>
    <div class="stat-card c-green"><div class="stat-label">已完成</div><div class="stat-value">{{ stats.done }}</div><div class="stat-sub">成功率 80.9%</div></div>
    <div class="stat-card c-orange"><div class="stat-label">流水线进行中</div><div class="stat-value">{{ stats.running }}</div><div class="stat-sub">3 个待人工确认</div></div>
    <div class="stat-card c-red"><div class="stat-label">发布失败</div><div class="stat-value">{{ stats.failed }}</div><div class="stat-sub">2 个上传超时</div></div>
    <div class="stat-card c-purple"><div class="stat-label">覆盖平台</div><div class="stat-value">{{ stats.platforms }}</div><div class="stat-sub">今日活跃 18 个</div></div>
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
