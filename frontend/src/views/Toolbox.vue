<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import http, { api } from '../api/http'

interface ToolField {
  key: string; label: string; type: string; default?: any; options?: { value: string; label: string }[] | string[]
  accept?: string; multiple?: boolean; hint?: string; show?: (form: Record<string, any>) => boolean
}
interface Tool {
  key: string; icon: string; name: string; desc: string; fields: ToolField[]
}

/* ═══ 工具定义 — 参数完整对齐单机版 ═══ */
const codecOptions = [
  { value: 'h264_nvenc', label: 'NVENC (NVIDIA GPU)' },
  { value: 'h264_amf', label: 'AMF (AMD GPU)' },
  { value: 'h264_qsv', label: 'QSV (Intel GPU)' },
  { value: 'libx264', label: 'libx264 (CPU)' },
]

const toolGroups = [
  { section: '视频处理', items: [
    { key: 'delogo', icon: '🔲', name: '遮盖四角水印', desc: '模糊遮盖视频四角水印区域',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'orient', label: '方向', type: 'select', default: 'auto', options: ['auto','portrait','landscape'] },
        { key: 'tl', label: '左上 (x:y:w:h)', type: 'text', default: '1:1:304:160' },
        { key: 'tr', label: '右上 (x:y:w:h)', type: 'text', default: '415:1:304:160' },
        { key: 'bl', label: '左下 (x:y:w:h)', type: 'text', default: '1:1119:304:160' },
        { key: 'br', label: '右下 (x:y:w:h)', type: 'text', default: '415:1119:304:160' },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
        { key: 'bitrate', label: '码率', type: 'text', default: '2M' },
      ]},
    { key: 'crop', icon: '✂️', name: '裁掉四角水印', desc: '裁剪掉四角水印区域',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'orient', label: '方向', type: 'select', default: 'auto', options: [
          { value: 'auto', label: '自动' },
          { value: 'portrait', label: '竖屏→720×960' },
          { value: 'landscape', label: '横屏→670×720' },
        ]},
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
        { key: 'bitrate', label: '码率', type: 'text', default: '2M' },
      ]},
    { key: 'blur-pad', icon: '🌫️', name: '虚化填充', desc: '模糊背景填充为标准尺寸',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'orient', label: '目标方向', type: 'select', default: 'auto', options: [
          { value: 'auto', label: '自动' },
          { value: 'landscape', label: '横屏 1280×720' },
          { value: 'portrait', label: '竖屏 720×1280' },
        ]},
        { key: 'strength', label: '模糊强度', type: 'text', default: '5:1' },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
        { key: 'bitrate', label: '码率', type: 'text', default: '2M' },
      ]},
    { key: 'trim', icon: '⏱️', name: '片头片尾处理', desc: '裁掉或添加片头片尾',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'mode', label: '模式', type: 'select', default: 'remove', options: [
          { value: 'remove', label: '去片头片尾' },
          { value: 'add', label: '加片头片尾' },
        ]},
        { key: 'start_sec', label: '去片头 (秒)', type: 'number', default: 0,
          show: (form: Record<string, any>) => form.mode === 'remove' },
        { key: 'end_sec', label: '去片尾 (秒)', type: 'number', default: 11,
          show: (form: Record<string, any>) => form.mode === 'remove' },
        { key: 'intro_file', label: '片头视频', type: 'file', accept: 'video/*',
          show: (form: Record<string, any>) => form.mode === 'add' },
        { key: 'outro_file', label: '片尾视频', type: 'file', accept: 'video/*',
          show: (form: Record<string, any>) => form.mode === 'add' },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
      ]},
    { key: 'concat', icon: '🔗', name: '视频合成', desc: '多段视频排序合并',
      fields: [
        { key: 'files', label: '选择视频（按顺序多选）', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'method', label: '合并方法', type: 'select', default: 'filter', options: [
          { value: 'filter', label: 'filter (兼容性好)' },
          { value: 'demuxer', label: 'demuxer (速度快)' },
        ]},
        { key: 'scale', label: '缩放', type: 'select', default: 'auto', options: ['auto','720p','1080p'] },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
      ]},
    { key: 'compress', icon: '📐', name: '视频压缩', desc: '批量压缩到指定大小',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'target_size_mb', label: '目标大小 (MB)', type: 'number', default: 100, hint: '超过此大小才会压缩' },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
      ]},
    { key: 'vid-watermark', icon: '🎬', name: '视频加水印', desc: 'MOV 动态四角轮转水印',
      fields: [
        { key: 'files', label: '选择视频', type: 'file', accept: 'video/*,.mp4,.mov,.avi,.mkv', multiple: true },
        { key: 'watermark', label: '水印文件 (PNG/MOV)', type: 'file', accept: '.png,.mov,image/png,video/quicktime' },
        { key: 'orient', label: '方向', type: 'select', default: 'auto', options: ['auto','portrait','landscape'] },
        { key: 'codec', label: '编码器', type: 'select', default: 'libx264', options: codecOptions },
        { key: 'bitrate', label: '码率', type: 'text', default: '2M' },
      ]},
  ]},
  { section: '图片处理', items: [
    { key: 'smart-cover', icon: '🖼️', name: '智能封面', desc: 'AI 从图片中生成封面',
      fields: [
        { key: 'files', label: '选择图片', type: 'file', accept: 'image/*,.jpg,.jpeg,.png,.webp', multiple: true },
        { key: 'layout', label: '拼接方式', type: 'select', default: 'triple', options: [
          { value: 'single', label: '单图' },
          { value: 'double', label: '双拼' },
          { value: 'triple', label: '三拼' },
          { value: 'wide', label: '宽屏' },
          { value: 'portrait', label: '竖版' },
        ]},
        { key: 'headroom', label: '头顶留白 %', type: 'number', default: 15 },
        { key: 'candidates', label: '候选数', type: 'number', default: 3 },
      ]},
    { key: 'img-watermark', icon: '🏷️', name: '图片加水印', desc: '批量加水印，人脸感知定位',
      fields: [
        { key: 'files', label: '选择图片', type: 'file', accept: 'image/*,.jpg,.jpeg,.png,.webp', multiple: true },
        { key: 'watermark', label: '水印图片', type: 'file', accept: 'image/png,.png' },
        { key: 'position', label: '水印位置', type: 'select', default: 'bottom-right', options: [
          { value: 'bottom-right', label: '右下角' },
          { value: 'bottom-left', label: '左下角' },
          { value: 'top-right', label: '右上角' },
          { value: 'top-left', label: '左上角' },
        ]},
        { key: 'wm_width', label: '水印宽度 (px)', type: 'number', default: 264 },
      ]},
    { key: 'convert-image', icon: '🔄', name: '图片格式转换', desc: 'WebP/PNG/JPG 批量转换',
      fields: [
        { key: 'files', label: '选择图片', type: 'file', accept: 'image/*,.jpg,.jpeg,.png,.webp,.gif,.bmp', multiple: true },
        { key: 'target_format', label: '目标格式', type: 'select', default: 'jpg', options: ['jpg','png','webp'] },
        { key: 'quality', label: '质量 (1-100)', type: 'number', default: 90 },
      ]},
  ]},
  { section: 'AI 工具', items: [
    { key: 'copywrite', icon: '🤖', name: '独立文案生成', desc: '脱离流水线单独生成文案',
      fields: [
        { key: 'protagonist', label: '主角', type: 'text' },
        { key: 'event', label: '事件', type: 'text' },
        { key: 'style', label: '文风', type: 'select', default: '反转打脸风',
          options: ['反转打脸风','搞笑玩梗风','麻辣吐槽风','深情共情风','悬念揭秘风'] },
        { key: 'body_len', label: '正文字数', type: 'number', default: 300 },
      ]},
  ]},
]

/* ═══ 状态 ═══ */
const activeTool = ref<Tool | null>(null)
const formData = ref<Record<string, any>>({})
const selectedFiles = ref<Record<string, File[]>>({})
const fileNames = ref<Record<string, string[]>>({})
const uploadProgress = ref(0)
const isUploading = ref(false)
const jobId = ref('')
const jobStatus = ref<any>(null)
const logLines = ref<string[]>([])
const polling = ref<number | null>(null)

function openTool(tool: Tool) {
  activeTool.value = tool
  formData.value = {}
  selectedFiles.value = {}
  fileNames.value = {}
  jobId.value = ''
  jobStatus.value = null
  logLines.value = []
  uploadProgress.value = 0
  for (const f of tool.fields) {
    formData.value[f.key] = f.default ?? ''
  }
}

function closeTool() {
  activeTool.value = null
  if (polling.value) { clearInterval(polling.value); polling.value = null }
}

/* 文件选择 */
function onFileSelected(fieldKey: string, e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  const files = Array.from(input.files)
  selectedFiles.value[fieldKey] = files
  fileNames.value[fieldKey] = files.map(f => f.name)
  input.value = '' // reset to allow re-select
}

/* 执行工具 */
async function runTool() {
  if (!activeTool.value) return
  logLines.value = []
  jobStatus.value = { status: 'uploading', progress: 0 }

  try {
    // 1. 上传文件
    const formPayload = new FormData()
    formPayload.append('tool_key', activeTool.value.key)

    // 添加非文件参数
    for (const f of activeTool.value.fields) {
      if (f.type !== 'file' && formData.value[f.key] !== undefined && formData.value[f.key] !== '') {
        formPayload.append(f.key, String(formData.value[f.key]))
      }
    }

    // 添加文件
    for (const f of activeTool.value.fields) {
      if (f.type === 'file' && selectedFiles.value[f.key]?.length) {
        for (const file of selectedFiles.value[f.key]) {
          formPayload.append(f.key, file)
        }
      }
    }

    isUploading.value = true
    uploadProgress.value = 0

    const res = await http.post('/tools/run', formPayload, {
      headers: { 'Content-Type': undefined },
      onUploadProgress: (e) => {
        if (e.total) {
          uploadProgress.value = Math.round((e.loaded / e.total) * 100)
          if (jobStatus.value) jobStatus.value.progress = uploadProgress.value
        }
      },
    })

    isUploading.value = false
    const data = res.data?.data ?? res.data
    jobId.value = data.job_id
    jobStatus.value = { status: 'running', progress: 0 }
    addLog('任务已提交，开始执行...', 'info')
    startPolling()
  } catch (e: any) {
    isUploading.value = false
    const detail = e.response?.data?.detail || e.response?.data?.message || '启动失败'
    jobStatus.value = { status: 'failed', error: detail }
    addLog('错误: ' + detail, 'error')
  }
}

function addLog(msg: string, level: string = 'info') {
  const ts = new Date().toLocaleTimeString()
  logLines.value.push(`[${ts}] [${level}] ${msg}`)
}

function startPolling() {
  if (polling.value) clearInterval(polling.value)
  polling.value = window.setInterval(async () => {
    if (!jobId.value) return
    try {
      const data = await api('GET', `/tools/job/${jobId.value}`)
      jobStatus.value = data
      if (data.logs?.length) {
        for (const l of data.logs) {
          if (!logLines.value.includes(l)) logLines.value.push(l)
        }
      }
      if (data.status === 'done' || data.status === 'failed') {
        if (polling.value) { clearInterval(polling.value); polling.value = null }
        if (data.status === 'done') addLog('执行完成 ✅', 'success')
        if (data.status === 'failed') addLog('执行失败: ' + (data.error || ''), 'error')
      }
    } catch {}
  }, 2000)
}

/* 是否显示字段（条件显示） */
function shouldShow(field: ToolField): boolean {
  if (!field.show) return true
  return field.show(formData.value)
}

/* 获取 select option 的显示文字 */
function optionLabel(opt: any): string {
  return typeof opt === 'string' ? opt : opt.label
}
function optionValue(opt: any): string {
  return typeof opt === 'string' ? opt : opt.value
}

onUnmounted(() => { if (polling.value) clearInterval(polling.value) })
</script>

<template>
  <div>
    <div class="section-header">
      <div class="section-title">工具箱</div>
    </div>
    <p style="font-size:12px;color:var(--t2);margin-bottom:20px">以下工具可独立使用，不在自动流水线内。点击工具卡片打开操作面板。</p>

    <template v-for="group in toolGroups" :key="group.section">
      <div style="font-size:12px;color:var(--t3);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px">{{ group.section }}</div>
      <div class="tool-grid">
        <div v-for="t in group.items" :key="t.key" class="tool-card" @click="openTool(t as Tool)">
          <div class="tc-icon">{{ t.icon }}</div>
          <div class="tc-name">{{ t.name }}</div>
          <div class="tc-desc">{{ t.desc }}</div>
        </div>
      </div>
    </template>

    <!-- ══════ 工具操作面板（Modal） ══════ -->
    <div v-if="activeTool" class="modal-overlay" @click.self="closeTool">
      <div class="modal" style="max-width:680px">
        <div class="modal-head">
          <div class="modal-title">{{ activeTool.icon }} {{ activeTool.name }}</div>
          <button style="background:none;border:none;color:var(--t2);font-size:24px;cursor:pointer" @click="closeTool">&times;</button>
        </div>
        <div class="modal-body">
          <template v-for="f in activeTool.fields" :key="f.key">
            <div v-if="shouldShow(f)" class="form-group" style="margin-bottom:14px">
              <label>{{ f.label }}</label>

              <!-- 文件选择 -->
              <div v-if="f.type === 'file'" style="display:flex;gap:10px;align-items:center">
                <label class="btn btn-primary" style="margin:0;cursor:pointer;white-space:nowrap;padding:6px 14px">
                  📁 选择{{ f.multiple ? '文件' : '文件' }}
                  <input type="file" :accept="f.accept || '*'" :multiple="f.multiple"
                         style="display:none" @change="onFileSelected(f.key, $event)" />
                </label>
                <span v-if="fileNames[f.key]?.length" style="font-size:12px;color:var(--green);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  已选 {{ fileNames[f.key].length }} 个文件
                </span>
                <span v-else style="font-size:12px;color:var(--t3)">未选择文件</span>
              </div>
              <!-- 文件列表展示 -->
              <div v-if="f.type === 'file' && fileNames[f.key]?.length"
                   style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px">
                <span v-for="name in fileNames[f.key]" :key="name"
                      style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--primary)">
                  {{ name }}
                </span>
              </div>

              <!-- 下拉选择 -->
              <select v-else-if="f.type === 'select'" v-model="formData[f.key]" class="form-select">
                <option v-for="o in f.options" :key="optionValue(o)" :value="optionValue(o)">{{ optionLabel(o) }}</option>
              </select>

              <!-- 数字输入 -->
              <input v-else-if="f.type === 'number'" v-model.number="formData[f.key]" type="number" class="form-input" />

              <!-- 文本输入 -->
              <input v-else v-model="formData[f.key]" class="form-input" :placeholder="f.label" />

              <div v-if="f.hint" class="form-hint">{{ f.hint }}</div>
            </div>
          </template>

          <!-- ── 执行状态 ── -->
          <div v-if="jobStatus" style="margin-top:16px;padding:14px;background:var(--bg3);border:1px solid var(--bd);border-radius:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
              <span style="font-size:12px;font-weight:600">执行状态</span>
              <span class="badge" :class="
                jobStatus.status==='done' ? 'badge-green' :
                jobStatus.status==='failed' ? 'badge-red' :
                jobStatus.status==='uploading' ? 'badge-orange' : 'badge-primary'
              " style="font-size:10px">
                {{ jobStatus.status === 'done' ? '✅ 完成' :
                   jobStatus.status === 'failed' ? '❌ 失败' :
                   jobStatus.status === 'uploading' ? '⬆️ 上传中' :
                   jobStatus.status === 'running' ? '⚙️ 执行中' : '等待' }}
              </span>
            </div>
            <div v-if="jobStatus.status==='uploading' || jobStatus.status==='running'"
                 class="progress-bar" style="height:6px;margin-bottom:6px">
              <div class="progress-fill" :style="{
                width: (jobStatus.progress || uploadProgress) + '%',
                background: jobStatus.status==='uploading' ? 'var(--orange)' : 'var(--primary)'
              }" />
            </div>
            <div v-if="jobStatus.error" style="font-size:11px;color:var(--red);margin-top:6px">{{ jobStatus.error }}</div>
            <div v-if="jobStatus.status==='done' && jobStatus.result" style="font-size:11px;color:var(--green);margin-top:6px">
              <template v-if="jobStatus.result.count">处理完成：{{ jobStatus.result.count }} 个文件</template>
              <template v-if="jobStatus.result.output_dir">输出目录：{{ jobStatus.result.output_dir }}</template>
            </div>
          </div>

          <!-- ── 日志输出 ── -->
          <div v-if="logLines.length" class="output-box">
            <div style="font-size:11px;font-weight:600;color:var(--t3);margin-bottom:6px">📋 执行日志</div>
            <div v-for="(line, i) in logLines" :key="i" style="font-size:11px;font-family:monospace;line-height:1.6"
                 :style="{ color: line.includes('[error]') ? 'var(--red)' : line.includes('[success]') ? 'var(--green)' : 'var(--t2)' }">
              {{ line }}
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeTool">关闭</button>
          <button class="btn btn-primary"
                  :disabled="isUploading || jobStatus?.status === 'running'"
                  @click="runTool">
            {{ isUploading ? '⬆️ 上传中...' : jobStatus?.status === 'running' ? '⚙️ 执行中...' : '▶ 执行' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.tool-card {
  background: var(--bg2);
  border: 1px solid var(--bd);
  border-radius: var(--radius);
  padding: 16px;
  cursor: pointer;
  transition: .2s;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.tool-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(79,195,247,.08);
}
.tc-icon { font-size: 26px; margin-bottom: 4px; }
.tc-name { font-size: 13px; font-weight: 600; }
.tc-desc { font-size: 11px; color: var(--t2); line-height: 1.4; }

.output-box {
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--bg1);
  border: 1px solid var(--bd);
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
}
</style>
