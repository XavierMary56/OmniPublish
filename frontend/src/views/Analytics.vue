<script setup lang="ts">
import { ref } from 'vue'

const period = ref('today')
const periods = ['今日','本周','本月','自定义']

const overviewStats = [
  { label:'总发帖量', val:'47', sub:'日均 42.3', cls:'c-primary' },
  { label:'成功率', val:'80.9%', sub:'目标 ≥85%', cls:'c-green' },
  { label:'平均流水线耗时', val:'6.2min', sub:'V1.0 人工基线 ~25min', cls:'c-purple' },
  { label:'人工介入率', val:'31%', sub:'文案确认 + 封面确认', cls:'c-orange' },
]

const platformStats = [
  { name:'91视频web', today:12, ok:11, fail:1, rate:'91.7%', avg:'5.8min', rateGreen:true },
  { name:'海角社区', today:9, ok:8, fail:1, rate:'88.9%', avg:'6.1min', rateGreen:false },
  { name:'黑料情报局', today:7, ok:6, fail:1, rate:'85.7%', avg:'5.4min', rateGreen:false },
  { name:'91porn', today:6, ok:6, fail:0, rate:'100%', avg:'4.2min', rateGreen:true },
  { name:'糖心', today:5, ok:4, fail:1, rate:'80.0%', avg:'7.0min', rateGreen:false },
  { name:'9色视频', today:4, ok:4, fail:0, rate:'100%', avg:'5.5min', rateGreen:true },
  { name:'海角社区 web', today:3, ok:3, fail:0, rate:'100%', avg:'6.8min', rateGreen:true },
  { name:'91暗网', today:1, ok:1, fail:0, rate:'100%', avg:'8.2min', rateGreen:true },
]

const editors = [
  { rank:'🥇', name:'张伟', count:18 },
  { rank:'🥈', name:'李梦', count:14 },
  { rank:'🥉', name:'王超', count:10 },
  { rank:'', name:'陈晓', count:5 },
]

const stepTimings = [
  { name:'文案生成', pct:20, color:'var(--primary)', time:'0.8min' },
  { name:'图片重命名', pct:5, color:'var(--green)', time:'0.1min' },
  { name:'封面制作', pct:25, color:'var(--orange)', time:'1.0min' },
  { name:'水印处理', pct:50, color:'var(--purple)', time:'2.1min' },
  { name:'上传发布', pct:55, color:'var(--red)', time:'2.2min' },
]
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">数据统计</div>
    <div class="filter-row">
      <button v-for="p in periods" :key="p" class="filter-btn" :class="{active: period===p}" @click="period=p">{{ p }}</button>
    </div>
  </div>

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
            <tr><td style="color:var(--t3)">其他 23 个平台</td><td>0</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>
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
        </div>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;display:inline-block}
.dot-blue{background:var(--primary)}
.dot-green{background:var(--green)}
.dot-orange{background:var(--orange)}
</style>
