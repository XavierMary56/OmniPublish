<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '../api/http'

const period = ref('今日')
const periods = ['今日','本周','本月','自定义']
const loading = ref(false)

// Period label -> API param mapping
const periodMap: Record<string, string> = {
  '今日': 'today',
  '本周': 'week',
  '本月': 'month',
  '自定义': 'all',
}

// Days in period for daily average calculation
function daysInPeriod(p: string): number {
  if (p === 'today') return 1
  if (p === 'week') return 7
  if (p === 'month') return 30
  return 1
}

// Step color mapping
const stepColorMap: Record<string, string> = {
  '素材': 'var(--primary)',
  '平台': 'var(--primary)',
  '文案': 'var(--green)',
  '重命名': 'var(--orange)',
  '封面': 'var(--purple)',
  '水印': 'var(--red)',
  '上传': 'var(--cyan, #00bcd4)',
}

function getStepColor(stepName: string): string {
  for (const [key, color] of Object.entries(stepColorMap)) {
    if (stepName.includes(key)) return color
  }
  return 'var(--primary)'
}

// Reactive data
const overviewStats = ref<Array<{ label: string; val: string; sub: string; cls: string }>>([])
const platformStats = ref<Array<{ name: string; today: number; ok: number; fail: number; rate: string; avg: string; rateGreen: boolean }>>([])
const totalPlatformCount = ref(0)
const editors = ref<Array<{ rank: string; name: string; count: number }>>([])
const stepTimings = ref<Array<{ name: string; pct: number; color: string; time: string }>>([])

async function loadData() {
  const apiPeriod = periodMap[period.value] ?? 'today'
  loading.value = true
  try {
    // Fetch all 4 endpoints in parallel
    const [overview, platforms, editorList, timings] = await Promise.all([
      api('GET', '/stats/overview', { period: apiPeriod }).catch(() => null),
      api('GET', '/stats/platforms', { period: apiPeriod }).catch(() => null),
      api('GET', '/stats/editors', { period: apiPeriod }).catch(() => null),
      api('GET', '/stats/pipeline-timing', { period: apiPeriod }).catch(() => null),
    ])

    // --- Overview stats (4 cards) ---
    const timingsArr = Array.isArray(timings) ? timings : []
    const totalMinutes = timingsArr.reduce((sum: number, t: any) => sum + (t.avg_minutes ?? 0), 0)
    const total = overview?.total ?? 0
    const awaitingConfirm = overview?.awaiting_confirm ?? 0
    const dailyAvg = total > 0 ? (total / daysInPeriod(apiPeriod)).toFixed(1) : '0'
    const interventionRate = total > 0
      ? (awaitingConfirm / total * 100).toFixed(1) + '%'
      : '—'

    overviewStats.value = [
      { label: '总发帖量', val: String(total), sub: `日均 ${dailyAvg}`, cls: 'c-primary' },
      { label: '成功率', val: (overview?.success_rate ?? 0) + '%', sub: '目标 ≥85%', cls: 'c-green' },
      { label: '平均流水线耗时', val: totalMinutes.toFixed(1) + 'min', sub: 'V1.0 人工基线 ~25min', cls: 'c-purple' },
      { label: '人工介入率', val: interventionRate, sub: '文案确认 + 封面确认', cls: 'c-orange' },
    ]

    // --- Platform stats table ---
    const platformArr = Array.isArray(platforms) ? platforms : []
    totalPlatformCount.value = overview?.platforms ?? platformArr.length
    platformStats.value = platformArr.map((p: any) => {
      const rate = p.total > 0 ? (p.success / p.total * 100) : 0
      return {
        name: p.name,
        today: p.total,
        ok: p.success,
        fail: p.failed,
        rate: rate.toFixed(1) + '%',
        avg: '—',
        rateGreen: rate >= 85,
      }
    })

    // --- Editor ranking ---
    const editorArr = Array.isArray(editorList) ? editorList : []
    const rankEmoji = ['🥇', '🥈', '🥉']
    editors.value = editorArr.map((e: any, i: number) => ({
      rank: rankEmoji[i] ?? '',
      name: e.display_name,
      count: e.total ?? e.done ?? 0,
    }))

    // --- Step timings bar chart ---
    const maxMin = timingsArr.length > 0
      ? Math.max(...timingsArr.map((t: any) => t.avg_minutes ?? 0), 0.01)
      : 1
    stepTimings.value = timingsArr.map((t: any) => ({
      name: t.name,
      pct: Math.round(((t.avg_minutes ?? 0) / maxMin) * 100),
      color: getStepColor(t.name),
      time: (t.avg_minutes ?? 0).toFixed(1) + 'min',
    }))
  } catch (e) {
    console.error('[Analytics] Failed to load stats:', e)
  } finally {
    loading.value = false
  }
}

// Load on mount and when period changes
onMounted(loadData)
watch(period, loadData)
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">数据统计</div>
    <div class="filter-row">
      <button v-for="p in periods" :key="p" class="filter-btn" :class="{active: period===p}" @click="period=p">{{ p }}</button>
    </div>
  </div>

  <!-- Loading overlay -->
  <div v-if="loading" style="text-align:center;padding:40px 0;color:var(--t3);font-size:13px">加载中…</div>

  <template v-else>
  <!-- Overview -->
  <div class="stats-row">
    <div v-for="s in overviewStats" :key="s.label" class="stat-card" :class="s.cls">
      <div class="stat-label">{{ s.label }}</div>
      <div class="stat-value">{{ s.val }}</div>
      <div class="stat-sub">{{ s.sub }}</div>
    </div>
  </div>

  <div style="display:flex;gap:16px;flex-wrap:wrap">
    <!-- Left: Platform Table -->
    <div style="flex:2;min-width:500px">
      <div class="panel">
        <div class="panel-title"><span class="dot dot-blue" /> 各平台发帖统计</div>
        <table style="width:100%;font-size:12px;border-collapse:collapse">
          <thead><tr>
            <th style="padding:8px 10px;font-size:11px">平台</th>
            <th style="padding:8px 10px;font-size:11px">今日发帖</th>
            <th style="padding:8px 10px;font-size:11px">成功</th>
            <th style="padding:8px 10px;font-size:11px">失败</th>
            <th style="padding:8px 10px;font-size:11px">成功率</th>
            <th style="padding:8px 10px;font-size:11px">平均耗时</th>
          </tr></thead>
          <tbody>
            <tr v-for="p in platformStats" :key="p.name">
              <td class="t1">{{ p.name }}</td>
              <td>{{ p.today }}</td>
              <td style="color:var(--green)">{{ p.ok }}</td>
              <td style="color:var(--red)">{{ p.fail }}</td>
              <td :style="{color: p.rateGreen ? 'var(--green)' : 'var(--t2)'}">{{ p.rate }}</td>
              <td>{{ p.avg }}</td>
            </tr>
            <tr v-if="totalPlatformCount > platformStats.length"><td style="color:var(--t3)">其他 {{ totalPlatformCount - platformStats.length }} 个平台</td><td>0</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Right: Editor Ranking + Step Timing -->
    <div style="flex:1;min-width:280px">
      <div class="panel">
        <div class="panel-title"><span class="dot dot-green" /> 各编辑发帖排名</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div v-for="e in editors" :key="e.name" style="display:flex;align-items:center;justify-content:space-between;font-size:13px">
            <span>{{ e.rank }} {{ !e.rank ? '' : '' }}<span :style="{paddingLeft: e.rank ? '0' : '24px'}">{{ e.name }}</span></span>
            <span :style="{color: e.count >= 10 ? 'var(--primary)' : 'var(--t2)', fontWeight: e.count >= 10 ? 700 : 400}">{{ e.count }} 篇</span>
          </div>
          <div v-if="editors.length === 0" style="color:var(--t3);font-size:12px;text-align:center;padding:12px 0">暂无数据</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title"><span class="dot dot-orange" /> 流水线各步骤耗时</div>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
          <div v-for="s in stepTimings" :key="s.name" style="display:flex;align-items:center;gap:10px">
            <span style="width:70px;color:var(--t3)">{{ s.name }}</span>
            <div style="flex:1;height:8px;background:var(--bg4);border-radius:4px;overflow:hidden">
              <div :style="{width:s.pct+'%',height:'100%',background:s.color,borderRadius:'4px'}" />
            </div>
            <span style="width:50px;text-align:right;color:var(--t2)">{{ s.time }}</span>
          </div>
          <div v-if="stepTimings.length === 0" style="color:var(--t3);font-size:12px;text-align:center;padding:12px 0">暂无数据</div>
        </div>
      </div>
    </div>
  </div>
  </template>
</div>
</template>

<style scoped>
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;display:inline-block}
.dot-blue{background:var(--primary)}
.dot-green{background:var(--green)}
.dot-orange{background:var(--orange)}
</style>
