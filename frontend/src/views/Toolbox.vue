<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { api } from '../api/http'

interface Tool {
  key: string; icon: string; name: string; desc: string
  fields: { key: string; label: string; type: string; default?: any; options?: string[] }[]
}

const toolGroups = [
  { section: '视频处理', items: [
    { key: 'delogo', icon: '🔲', name: '遮盖四角水印', desc: '模糊遮盖视频四角水印区域',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'orient', label: '方向', type: 'select', default: 'auto', options: ['auto','portrait','landscape'] },
      ]},
    { key: 'crop', icon: '✂️', name: '裁掉四角水印', desc: '裁剪掉四角水印区域',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'orient', label: '方向', type: 'select', default: 'auto', options: ['auto','portrait','landscape'] },
      ]},
    { key: 'blur-pad', icon: '🌫️', name: '虚化填充', desc: '模糊背景填充为标准尺寸',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'strength', label: '模糊强度', type: 'text', default: '5:1' },
      ]},
    { key: 'trim', icon: '⏱️', name: '片头片尾处理', desc: '裁掉片头片尾',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'start_sec', label: '裁掉片头(秒)', type: 'number', default: 0 },
        { key: 'end_sec', label: '裁掉片尾(秒)', type: 'number', default: 11 },
      ]},
    { key: 'intro-outro', icon: '🎬', name: '加片头片尾', desc: '添加片头片尾视频',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'intro', label: '片头文件路径', type: 'text' },
        { key: 'outro', label: '片尾文件路径', type: 'text' },
      ]},
    { key: 'concat', icon: '🔗', name: '视频合成', desc: '多段视频排序合并',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'method', label: '方法', type: 'select', default: 'demuxer', options: ['demuxer','filter'] },
      ]},
    { key: 'compress', icon: '📐', name: '视频压缩', desc: '批量压缩到指定大小',
      fields: [
        { key: 'input_dir', label: '输入文件夹', type: 'text' },
        { key: 'target_size_mb', label: '目标大小(MB)', type: 'number', default: 100 },
      ]},
  ]},
  { section: '图片处理', items: [
    { key: 'smart-cover', icon: '🖼️', name: '智能封面', desc: 'AI 从图片中生成封面',
      fields: [
        { key: 'input_dir', label: '图片文件夹', type: 'text' },
        { key: 'layout', label: '布局', type: 'select', default: 'triple', options: ['single','double','triple','wide','portrait'] },
        { key: 'candidates', label: '候选数', type: 'number', default: 3 },
      ]},
    { key: 'convert-image', icon: '🔄', name: '图片格式转换', desc: 'WebP/PNG/JPG 批量转换',
      fields: [
        { key: 'input_dir', label: '图片文件夹', type: 'text' },
        { key: 'target_format', label: '目标格式', type: 'select', default: 'jpg', options: ['jpg','png','webp'] },
      ]},
  ]},
  { section: 'AI 工具', items: [
    { key: 'copywrite', icon: '🤖', name: '独立文案生成', desc: '脱离流水线单独生成文案',
      fields: [
        { key: 'protagonist', label: '主角', type: 'text' },
        { key: 'event', label: '事件', type: 'text' },
        { key: 'style', label: '文风', type: 'select', default: '反转打脸风', options: ['反转打脸风','搞笑玩梗风','麻辣吐槽风','深情共情风','悬念揭秘风'] },
        { key: 'body_len', label: '正文字数', type: 'number', default: 300 },
      ]},
  ]},
]

const activeTool = ref<Tool | null>(null)
const formData = ref<Record<string, any>>({})
const jobId = ref('')
const jobStatus = ref<any>(null)
const polling = ref<number | null>(null)

function openTool(tool: Tool) {
  activeTool.value = tool
  formData.value = {}
  jobId.value = ''
  jobStatus.value = null
  for (const f of tool.fields) {
    formData.value[f.key] = f.default ?? ''
  }
}

function closeTool() {
  activeTool.value = null
  if (polling.value) { clearInterval(polling.value); polling.value = null }
}

async function runTool() {
  if (!activeTool.value) return
  try {
    const data = await api('POST', `/tools/${activeTool.value.key}`, formData.value)
    jobId.value = data.job_id
    startPolling()
  } catch (e: any) {
    jobStatus.value = { status: 'failed', error: e.response?.data?.detail || '启动失败' }
  }
}

function startPolling() {
  if (polling.value) clearInterval(polling.value)
  polling.value = window.setInterval(async () => {
    if (!jobId.value) return
    try {
      const data = await api('GET', `/tools/${jobId.value}/status`)
      jobStatus.value = data
      if (data.status === 'done' || data.status === 'failed') {
        if (polling.value) { clearInterval(polling.value); polling.value = null }
      }
    } catch {}
  }, 1500)
}

onUnmounted(() => { if (polling.value) clearInterval(polling.value) })
</script>

<template>
  <div>
    <div style="font-size:16px;font-weight:700;margin-bottom:6px">工具箱</div>
    <p style="font-size:12px;color:var(--t2);margin-bottom:20px">以下工具可独立使用，不在自动流水线内。点击工具卡片打开操作面板。</p>

    <template v-for="group in toolGroups" :key="group.section">
      <div style="font-size:12px;color:var(--t3);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">{{ group.section }}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:24px">
        <div v-for="t in group.items" :key="t.key"
             style="background:var(--bg2);border:1px solid var(--bd);border-radius:var(--radius);padding:16px;cursor:pointer;transition:.2s;display:flex;flex-direction:column;gap:5px"
             @click="openTool(t as Tool)"
             @mouseenter="($event.currentTarget as HTMLElement).style.borderColor='var(--primary)';($event.currentTarget as HTMLElement).style.transform='translateY(-2px)'"
             @mouseleave="($event.currentTarget as HTMLElement).style.borderColor='var(--bd)';($event.currentTarget as HTMLElement).style.transform=''">
          <div style="font-size:24px">{{ t.icon }}</div>
          <div style="font-size:13px;font-weight:600">{{ t.name }}</div>
          <div style="font-size:11px;color:var(--t2);line-height:1.4">{{ t.desc }}</div>
        </div>
      </div>
    </template>

    <!-- Tool Modal -->
    <div v-if="activeTool" class="modal-overlay" @click.self="closeTool">
      <div class="modal" style="max-width:600px">
        <div class="modal-head">
          <div class="modal-title">{{ activeTool.icon }} {{ activeTool.name }}</div>
          <button style="background:none;border:none;color:var(--t2);font-size:24px;cursor:pointer" @click="closeTool">&times;</button>
        </div>
        <div class="modal-body">
          <div v-for="f in activeTool.fields" :key="f.key" class="form-group" style="margin-bottom:14px">
            <label>{{ f.label }}</label>
            <select v-if="f.type==='select'" v-model="formData[f.key]" class="form-select">
              <option v-for="o in f.options" :key="o" :value="o">{{ o }}</option>
            </select>
            <input v-else-if="f.type==='number'" v-model.number="formData[f.key]" type="number" class="form-input" />
            <input v-else v-model="formData[f.key]" class="form-input" :placeholder="f.label" />
          </div>

          <!-- 执行状态 -->
          <div v-if="jobStatus" style="margin-top:16px;padding:14px;background:var(--bg3);border-radius:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <span style="font-size:12px;font-weight:600">执行状态</span>
              <span class="badge" :class="jobStatus.status==='done'?'badge-green':jobStatus.status==='failed'?'badge-red':'badge-primary'" style="font-size:10px">
                {{ jobStatus.status === 'done' ? '完成' : jobStatus.status === 'failed' ? '失败' : jobStatus.status === 'running' ? '执行中' : '等待' }}
              </span>
            </div>
            <div v-if="jobStatus.status==='running'" class="progress-bar" style="height:6px;margin-bottom:6px">
              <div class="progress-fill" :style="{width:jobStatus.progress+'%',background:'var(--primary)'}" />
            </div>
            <div v-if="jobStatus.error" style="font-size:11px;color:var(--red);margin-top:6px">{{ jobStatus.error }}</div>
            <div v-if="jobStatus.status==='done' && jobStatus.result" style="font-size:11px;color:var(--green);margin-top:6px">
              <template v-if="jobStatus.result.count">处理完成：{{ jobStatus.result.count }} 个文件</template>
              <template v-if="jobStatus.result.title">标题：{{ jobStatus.result.title }}</template>
              <template v-if="jobStatus.result.covers">生成 {{ jobStatus.result.covers.length }} 个封面</template>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeTool">关闭</button>
          <button class="btn btn-primary"
                  :disabled="jobStatus?.status === 'running'"
                  @click="runTool">
            {{ jobStatus?.status === 'running' ? '⏳ 执行中...' : '▶ 执行' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
