<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { usePipelineStore } from '../stores/pipeline'
import { api } from '../api/http'

const route = useRoute()
const store = usePipelineStore()

// Step 1 state
const platforms = ref<any[]>([])
const platformSearch = ref('')
const folder = ref('')
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)

const localPathInput = ref('')
const wmPlan = ref<any[]>([])

// 平台 ID → 名称映射（从平台列表构建）
const platformNameMap = computed(() => {
  const map: Record<number, string> = {}
  for (const p of platforms.value) {
    map[p.id] = p.name
  }
  return map
})

async function retryPlatform(platformId: number) {
  if (!store.taskId) return
  try {
    await api('POST', `/pipeline/${store.taskId}/step/6/retry`, { platform_id: platformId })
  } catch (e: any) {
    alert(e.response?.data?.detail || '重试失败')
  }
}

// 封面图片 URL 转换（容器路径 → 浏览器可访问路径）
function coverUrl(path: string): string {
  // /app/backend/uploads/tasks/xxx/cover_0.jpg → /uploads/tasks/xxx/cover_0.jpg
  if (path.startsWith('/app/backend/uploads/')) {
    return path.replace('/app/backend/uploads/', '/uploads/')
  }
  if (path.startsWith('/uploads/')) return path
  // 相对路径
  return `/uploads/${path}`
}

// Step 2 state
const copyForm = ref({ protagonist: '', event: '', photos: '', video_desc: '', style: '反转打脸风', author: '编辑', categories: [] as string[] })
const editTitle = ref('')
const editKeywords = ref('')
const editBody = ref('')

// Step 3 state
const prefix = ref('')
const startNum = ref(1)
const separator = ref('_')

// Step 4 state
const customCategory = ref('')
function addCustomCategory() {
  const c = customCategory.value.trim()
  if (c && !copyForm.value.categories.includes(c)) {
    copyForm.value.categories.push(c)
  }
  customCategory.value = ''
}

const coverLayout = ref('triple')
const coverSize = ref('1300x640')
const coverHeadroom = ref(15)

const stepNames = ['素材 & 平台', '文案生成', '图片重命名', '封面制作', '水印处理', '上传 & 发布']

// 按部组分组
const groupedPlatforms = computed(() => {
  const groups: Record<string, any[]> = {}
  const q = platformSearch.value.toLowerCase()
  for (const p of platforms.value) {
    if (q && !p.name.toLowerCase().includes(q) && !p.dept.includes(q)) continue
    if (!groups[p.dept]) groups[p.dept] = []
    groups[p.dept].push(p)
  }
  return groups
})

const selectedSet = computed(() => new Set(store.selectedPlatforms))

function togglePlatform(id: number) {
  const idx = store.selectedPlatforms.indexOf(id)
  if (idx >= 0) store.selectedPlatforms.splice(idx, 1)
  else store.selectedPlatforms.push(id)
}

function selectAllGroup(dept: string) {
  const ids = (groupedPlatforms.value[dept] || []).map((p: any) => p.id)
  const allSelected = ids.every((id: number) => selectedSet.value.has(id))
  for (const id of ids) {
    const idx = store.selectedPlatforms.indexOf(id)
    if (allSelected && idx >= 0) store.selectedPlatforms.splice(idx, 1)
    else if (!allSelected && idx < 0) store.selectedPlatforms.push(id)
  }
}

// 拖拽上传
function onDragOver(e: DragEvent) { e.preventDefault(); isDragging.value = true }
function onDragLeave() { isDragging.value = false }

async function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  const items = e.dataTransfer?.items
  if (!items) return
  const files: File[] = []
  for (let i = 0; i < items.length; i++) {
    const entry = items[i].webkitGetAsEntry?.()
    if (entry) {
      await collectFiles(entry, files)
    } else {
      const f = items[i].getAsFile()
      if (f) files.push(f)
    }
  }
  if (files.length) await store.uploadFiles(files)
}

async function collectFiles(entry: any, files: File[]): Promise<void> {
  if (entry.isFile) {
    const f: File = await new Promise(r => entry.file(r))
    files.push(f)
  } else if (entry.isDirectory) {
    const reader = entry.createReader()
    const entries: any[] = await new Promise(r => reader.readEntries(r))
    for (const e of entries) await collectFiles(e, files)
  }
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    store.uploadFiles(Array.from(input.files))
    input.value = ''
  }
}

function triggerUploadFolder() {
  folderInput.value?.click()
}
function triggerUploadFiles() {
  fileInput.value?.click()
}

async function handleLocalPath() {
  const path = localPathInput.value.trim()
  if (!path) return
  try {
    await store.useLocalPath(path)
  } catch (e: any) {
    alert(e.response?.data?.detail || e.message || '路径加载失败')
  }
}

// Step navigation
function canNext(): boolean {
  if (store.currentStep === 0) return store.selectedPlatforms.length > 0 && store.fileManifest.images.length + store.fileManifest.videos.length > 0
  if (store.currentStep === 1) return !!editTitle.value
  return true
}

async function handleNext() {
  if (store.currentStep === 0) {
    await store.createTask(store.folderPath, store.selectedPlatforms)
    await store.loadCategories()
    // 自动从 TXT 提取内容填充文案表单
    autoFillFromTxt()
  }
}

/** 从上传的 TXT 文件内容自动填充文案输入 */
function autoFillFromTxt() {
  const contents = store.fileManifest.txt_contents
  if (!contents || Object.keys(contents).length === 0) return

  // 合并所有 TXT 内容
  const allText = Object.values(contents).join('\n\n').trim()
  if (!allText) return

  // 尝试解析结构化内容（标题:xxx 主角:xxx 等）
  const lines = allText.split('\n').map(l => l.trim()).filter(Boolean)

  let protagonist = ''
  let event = ''
  let photos = ''
  let videoDesc = ''
  let body = ''
  const bodyLines: string[] = []

  for (const line of lines) {
    const lower = line.toLowerCase()
    // 匹配 "主角：xxx" 或 "主角:xxx" 格式
    const kv = line.match(/^(主角|角色|人物|protagonist)[：:]\s*(.+)/i)
    if (kv) { protagonist = kv[2].trim(); continue }

    const ev = line.match(/^(事件|事情|描述|event)[：:]\s*(.+)/i)
    if (ev) { event = ev[2].trim(); continue }

    const ph = line.match(/^(照片|图片|photos?)[：:]\s*(.+)/i)
    if (ph) { photos = ph[2].trim(); continue }

    const vd = line.match(/^(视频|video)[：:]\s*(.+)/i)
    if (vd) { videoDesc = vd[2].trim(); continue }

    // 其他行视为正文补充
    bodyLines.push(line)
  }

  // 如果没有结构化字段，把整段内容当事件描述
  if (!protagonist && !event && bodyLines.length > 0) {
    // 第一行当主角，第二行当事件，剩下当补充
    if (bodyLines.length >= 2) {
      protagonist = bodyLines[0]
      event = bodyLines[1]
    } else {
      event = bodyLines[0]
    }
  }

  // 填充表单（只填空的字段，不覆盖用户已填内容）
  if (protagonist && !copyForm.value.protagonist) copyForm.value.protagonist = protagonist
  if (event && !copyForm.value.event) copyForm.value.event = event
  if (photos && !copyForm.value.photos) copyForm.value.photos = photos
  if (videoDesc && !copyForm.value.video_desc) copyForm.value.video_desc = videoDesc

  // 图片/视频数量自动填充
  if (!copyForm.value.photos && store.fileManifest.images.length > 0) {
    copyForm.value.photos = `${store.fileManifest.images.length}张图片`
  }
  if (!copyForm.value.video_desc && store.fileManifest.videos.length > 0) {
    copyForm.value.video_desc = `${store.fileManifest.videos.length}段视频`
  }
}

// 返回上一步
function handlePrev() {
  if (store.currentStep > 0) {
    store.currentStep = store.currentStep - 1
  }
}

// Step 3 重命名预览 — 本地实时计算
const renamePreviewLocal = computed(() => {
  const images = store.fileManifest.images
  if (!images.length || !prefix.value) return []
  const digits = String(images.length + startNum.value - 1).length
  return images.map((f: string, i: number) => {
    const num = String(startNum.value + i).padStart(digits, '0')
    const ext = f.substring(f.lastIndexOf('.'))
    return { old: f, new: `${prefix.value}${separator.value}${num}${ext}` }
  })
})

// Step 6 发布按钮是否可用
const canPublish = computed(() => {
  const statuses = Object.values(store.publishStatus)
  return statuses.length > 0 && statuses.some((s: any) => s.status !== 'published')
})

async function handleGenerateCopy() {
  if (!copyForm.value.protagonist.trim()) {
    alert('请填写主角')
    return
  }
  if (!copyForm.value.event.trim()) {
    alert('请填写事件')
    return
  }
  try {
    await store.generateCopy(copyForm.value)
  } catch (e: any) {
    const msg = e.response?.data?.detail || e.message || '文案生成请求失败'
    alert(typeof msg === 'string' ? msg : JSON.stringify(msg))
    store.isGenerating = false
  }
}

async function handleConfirmCopy() {
  await store.confirmCopy(editTitle.value, editKeywords.value, editBody.value, copyForm.value.author, copyForm.value.categories)
  prefix.value = editTitle.value.slice(0, 20)
}

async function handleConfirmRename() {
  await store.confirmRename(prefix.value, startNum.value, 2, separator.value)
}

const isGeneratingCover = ref(false)
let coverPollTimer: number | null = null

async function handleGenerateCover() {
  isGeneratingCover.value = true
  store.coverCandidates = []
  try {
    await store.generateCover(coverLayout.value, 3, coverHeadroom.value)
    // 轮询等待封面生成完成
    if (coverPollTimer) clearInterval(coverPollTimer)
    coverPollTimer = window.setInterval(async () => {
      if (!store.taskId) return
      try {
        const data = await api('GET', `/pipeline/${store.taskId}`)
        const step3 = (data.steps || []).find((s: any) => s.step === 3)
        if (step3 && (step3.status === 'awaiting_confirm' || step3.status === 'done')) {
          isGeneratingCover.value = false
          let stepData = step3.data
          if (typeof stepData === 'string') try { stepData = JSON.parse(stepData) } catch {}
          if (stepData?.candidates) store.coverCandidates = stepData.candidates
          await store.loadTask(store.taskId!)
          if (coverPollTimer) { clearInterval(coverPollTimer); coverPollTimer = null }
        } else if (step3?.status === 'failed') {
          isGeneratingCover.value = false
          alert('封面生成失败: ' + (step3.error || '未知错误'))
          if (coverPollTimer) { clearInterval(coverPollTimer); coverPollTimer = null }
        }
      } catch {}
    }, 3000)
  } catch (e: any) {
    isGeneratingCover.value = false
    alert(e.response?.data?.detail || '封面生成失败')
  }
}

const showImagePicker = ref(false)
const pickerSelectedImages = ref<string[]>([])

function openImagePicker() {
  pickerSelectedImages.value = []
  showImagePicker.value = true
}

function togglePickerImage(img: string) {
  const idx = pickerSelectedImages.value.indexOf(img)
  if (idx >= 0) pickerSelectedImages.value.splice(idx, 1)
  else pickerSelectedImages.value.push(img)
}

async function confirmPickerImages() {
  if (!pickerSelectedImages.value.length || !store.taskId) return
  // 用选中的图片生成封面
  try {
    await api('POST', `/pipeline/${store.taskId}/step/4/generate`, {
      layout: coverLayout.value,
      candidates: 1,
      head_margin: coverHeadroom.value,
      selected_images: pickerSelectedImages.value,
    })
    showImagePicker.value = false
    isGeneratingCover.value = true
    // 复用封面轮询
    handleGenerateCover()
  } catch (e: any) {
    alert(e.response?.data?.detail || '生成失败')
  }
}

async function handleConfirmCover() {
  await store.confirmCover(store.selectedCover)
}

async function handleConfirmWatermark() {
  await store.confirmWatermark()
}

async function handlePublish() {
  await store.publish()
}

// 监听文案生成结果
watch(() => store.copyResult, (r) => {
  if (r) {
    editTitle.value = r.title
    editKeywords.value = r.keywords
    editBody.value = r.body
  }
})

// 监听步骤变化，加载对应数据
watch(() => store.currentStep, async (step) => {
  // 进入 Step 5 时加载水印方案预览
  if (step === 4 && store.taskId) {
    try {
      const plan = await api('GET', `/pipeline/${store.taskId}/step/5/plan`)
      wmPlan.value = plan.platforms || plan || []
    } catch { wmPlan.value = [] }
  }
})

const hasDraft = ref(false)

onMounted(async () => {
  // 加载平台列表
  try { platforms.value = await api('GET', '/platforms') } catch {}

  // 如果有 ID 参数，加载已有任务
  const id = route.params.id
  if (id) {
    await store.loadTask(Number(id))
    if (store.copyResult) {
      editTitle.value = store.copyResult.title
      editKeywords.value = store.copyResult.keywords
      editBody.value = store.copyResult.body
    }
    prefix.value = store.renamePrefix
    folder.value = store.folderPath
  } else {
    // 尝试恢复草稿
    if (store.loadDraft()) {
      hasDraft.value = true
      if (store.copyResult) {
        editTitle.value = store.copyResult.title
        editKeywords.value = store.copyResult.keywords
        editBody.value = store.copyResult.body
      }
      prefix.value = store.renamePrefix
      folder.value = store.folderPath
    } else {
      store.reset()
    }
    // 获取预估任务编号（新建时显示）
    if (!store.taskNo) {
      try {
        const res = await api('GET', '/pipeline/next-no')
        store.taskNo = res.task_no
      } catch {}
    }
  }
})

function handleSaveDraft() {
  store.saveDraft()
  alert('草稿已保存')
}

function handleDiscardDraft() {
  store.clearDraft()
  store.reset()
  hasDraft.value = false
}
</script>

<template>
  <div>
    <div class="wizard-wrap">
      <!-- Header -->
      <div style="padding:20px 24px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;align-items:center;gap:12px">
          <h3 style="font-size:16px;font-weight:700">
            {{ store.taskId ? '发帖任务' : '新建发帖任务' }}
            <span style="color:var(--primary)">{{ store.taskNo || '' }}</span>
          </h3>
          <span v-if="store.taskId" style="font-size:11px;color:var(--t3);background:var(--bg4);padding:2px 8px;border-radius:4px">
            ID:{{ store.taskId }}
          </span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span class="badge badge-primary" style="font-size:10px">● 流水线模式</span>
          <button class="btn btn-ghost btn-sm" @click="handleSaveDraft">💾 保存草稿</button>
        </div>
      </div>
      <!-- 草稿恢复提示 -->
      <div v-if="hasDraft && !store.taskId" style="padding:10px 24px;background:rgba(255,183,77,.08);border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:12px;color:var(--orange)">📋 已恢复上次未完成的草稿</span>
        <button class="btn btn-sm" style="color:var(--red);font-size:11px" @click="handleDiscardDraft">丢弃草稿</button>
      </div>

      <!-- Step indicators -->
      <div style="display:flex;align-items:center;padding:18px 24px;border-bottom:1px solid var(--bd);overflow-x:auto">
        <template v-for="(name, i) in stepNames" :key="i">
          <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
            <div :style="{
              width:'30px',height:'30px',borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',
              fontSize:'13px',fontWeight:700,border:'2px solid',flexShrink:0,
              ...(i < store.currentStep ? {background:'var(--green-dim)',color:'var(--green)',borderColor:'var(--green)'}
                : i === store.currentStep ? {background:'var(--primary)',color:'#000',borderColor:'var(--primary)'}
                : {background:'var(--bg4)',color:'var(--t3)',borderColor:'var(--bd)'}),
            }">{{ i + 1 }}</div>
            <span :style="{fontSize:'12px',color: i<store.currentStep?'var(--green)':i===store.currentStep?'var(--t1)':'var(--t3)',fontWeight:i===store.currentStep?600:400}">{{ name }}</span>
          </div>
          <div v-if="i < 5" :style="{flex:1,height:'2px',minWidth:'20px',maxWidth:'50px',margin:'0 8px',background:i<store.currentStep?'var(--green)':'var(--bd)'}" />
        </template>
      </div>

      <!-- Step panels -->
      <div style="padding:28px 24px;min-height:400px">

        <!-- Step 1: 素材 & 平台 -->
        <div v-if="store.currentStep === 0">
          <div style="display:flex;gap:20px;flex-wrap:wrap">
            <div style="flex:1;min-width:300px">
              <h4 style="margin-bottom:12px;font-size:14px">素材文件夹</h4>

              <!-- 拖拽上传区域 -->
              <div class="upload-zone"
                   :class="{ dragging: isDragging, uploaded: store.fileManifest.images.length > 0 || store.fileManifest.videos.length > 0 || store.fileManifest.txts.length > 0 }"
                   @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
                <input ref="fileInput" type="file" multiple accept="image/*,video/*,.txt,.mp4,.mov,.avi,.mkv" style="display:none" @change="onFileSelect" />
                <input ref="folderInput" type="file" webkitdirectory style="display:none" @change="onFileSelect" />

                <!-- 上传中 -->
                <template v-if="store.isUploading">
                  <div class="upload-icon">⏳</div>
                  <div class="upload-hint">上传中… {{ store.uploadProgress }}%</div>
                  <div class="progress-bar" style="margin-top:10px;height:6px;max-width:300px;margin-left:auto;margin-right:auto">
                    <div class="progress-fill" :style="{width: store.uploadProgress + '%', background: 'var(--primary)'}" />
                  </div>
                </template>

                <!-- 已上传，显示识别结果 -->
                <template v-else-if="store.fileManifest.images.length > 0 || store.fileManifest.videos.length > 0 || store.fileManifest.txts.length > 0">
                  <div style="width:100%;text-align:left">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                      <span style="font-size:20px">📂</span>
                      <span style="font-size:14px;font-weight:600;color:var(--green)">素材已就绪 ✅</span>
                      <div style="margin-left:auto;display:flex;gap:6px">
                        <button class="btn btn-ghost btn-sm" @click.stop="triggerUploadFiles()">📎 追加文件</button>
                        <button class="btn btn-ghost btn-sm" @click.stop="triggerUploadFolder()">📁 追加文件夹</button>
                      </div>
                    </div>
                    <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px">
                      <div style="display:flex;align-items:center;gap:6px;font-size:13px">
                        <span>🖼️</span>
                        <span>图片 × <strong style="color:var(--primary)">{{ store.fileManifest.images.length }}</strong></span>
                        <span v-if="store.fileManifest.images.length > 0 && store.fileManifest.images.length <= 6" style="font-size:11px;color:var(--t3)">
                          ({{ store.fileManifest.images[0] }} ~ {{ store.fileManifest.images[store.fileManifest.images.length - 1] }})
                        </span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px;font-size:13px">
                        <span>🎬</span>
                        <span>视频 × <strong style="color:var(--primary)">{{ store.fileManifest.videos.length }}</strong></span>
                        <span v-if="store.fileManifest.videos.length > 0" style="font-size:11px;color:var(--t3)">
                          ({{ store.fileManifest.videos.join(', ') }})
                        </span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px;font-size:13px">
                        <span>📄</span>
                        <span>文案 × <strong :style="{color: store.fileManifest.txts.length ? 'var(--primary)' : 'var(--t3)'}">{{ store.fileManifest.txts.length }}</strong></span>
                        <span v-if="!store.fileManifest.txts.length" style="font-size:11px;color:var(--t3)">(未检测到 TXT)</span>
                      </div>
                    </div>
                    <!-- 文件名标签 -->
                    <div v-if="store.fileManifest.images.length > 0 && store.fileManifest.images.length <= 20" style="display:flex;flex-wrap:wrap;gap:4px">
                      <span v-for="f in store.fileManifest.images" :key="f" style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--t2)">🖼️ {{ f }}</span>
                      <span v-for="f in store.fileManifest.videos" :key="f" style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--orange)">🎬 {{ f }}</span>
                      <span v-for="f in store.fileManifest.txts" :key="f" style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--green)">📄 {{ f }}</span>
                    </div>
                  </div>
                </template>

                <!-- 初始状态 -->
                <template v-else>
                  <div class="upload-icon">📁</div>
                  <div class="upload-hint">拖入素材文件夹</div>
                  <div class="upload-sub" style="margin-bottom:10px">支持：图片（JPG/PNG/WebP）、视频（MP4/MOV）、文案（TXT）</div>
                  <div style="display:flex;gap:8px;justify-content:center" @click.stop>
                    <button class="btn btn-primary btn-sm" @click="triggerUploadFolder()">📁 选择文件夹</button>
                    <button class="btn btn-ghost btn-sm" @click="triggerUploadFiles()">📎 选择文件</button>
                  </div>
                </template>
              </div>

              <!-- 本地路径输入（Docker 挂载目录，免上传） -->
              <div style="margin-top:10px">
                <div style="font-size:11px;color:var(--t3);margin-bottom:4px">或输入服务器本地路径（免上传，秒级加载）</div>
                <div style="display:flex;gap:8px">
                  <input v-model="localPathInput" class="form-input" style="flex:1"
                         placeholder="/mnt/素材/item_20260410/OmniPublish_V2/task1/task1" />
                  <button class="btn btn-ghost" style="white-space:nowrap" @click="handleLocalPath"
                          :disabled="!localPathInput.trim() || store.isUploading">
                    📂 加载
                  </button>
                </div>
              </div>

              <!-- 文件识别结果 -->
              <div v-if="store.fileManifest.images.length > 0 || store.fileManifest.videos.length > 0"
                   style="margin-top:10px;padding:12px 14px;background:var(--bg3);border:1px solid var(--bd);border-radius:8px;font-size:12px;color:var(--t2)">
                <div style="font-weight:600;color:var(--t1);margin-bottom:8px">📂 已识别文件：</div>
                <div style="display:flex;gap:16px;flex-wrap:wrap">
                  <div style="display:flex;align-items:center;gap:6px">
                    <span>🖼️</span>
                    <span>图片 × <strong style="color:var(--primary)">{{ store.fileManifest.images.length }}</strong></span>
                  </div>
                  <div style="display:flex;align-items:center;gap:6px">
                    <span>🎬</span>
                    <span>视频 × <strong style="color:var(--primary)">{{ store.fileManifest.videos.length }}</strong></span>
                  </div>
                  <div style="display:flex;align-items:center;gap:6px">
                    <span>📄</span>
                    <span>文案 × <strong :style="{color: store.fileManifest.txts.length ? 'var(--primary)' : 'var(--t3)'}">{{ store.fileManifest.txts.length }}</strong></span>
                    <span v-if="!store.fileManifest.txts.length" style="color:var(--t3)">(未检测到 TXT)</span>
                  </div>
                </div>
                <!-- 文件列表 -->
                <div v-if="store.fileManifest.images.length <= 12" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px">
                  <span v-for="f in store.fileManifest.images" :key="f" style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--t3)">{{ f }}</span>
                </div>
                <div v-else style="margin-top:6px;font-size:11px;color:var(--t3)">
                  {{ store.fileManifest.images[0] }} ~ {{ store.fileManifest.images[store.fileManifest.images.length - 1] }}
                </div>
                <div v-if="store.fileManifest.videos.length" style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">
                  <span v-for="f in store.fileManifest.videos" :key="f" style="font-size:10px;padding:2px 6px;background:var(--bg4);border-radius:4px;color:var(--orange)">{{ f }}</span>
                </div>
              </div>
            </div>
            <div style="flex:1.5;min-width:400px">
              <h4 style="margin-bottom:12px;font-size:14px">选择发布平台</h4>
              <input v-model="platformSearch" class="form-input" placeholder="搜索平台名称…" style="margin-bottom:10px" />
              <div v-for="(items, dept) in groupedPlatforms" :key="dept" style="margin-bottom:12px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                  <span style="font-size:12px;font-weight:600;color:var(--t2)">{{ dept }}</span>
                  <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;color:var(--primary);border:1px solid var(--primary)" @click="selectAllGroup(dept as string)">全选</button>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px">
                  <div v-for="p in items" :key="p.id"
                       style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:8px;border:1px solid var(--bd);background:var(--bg3);cursor:pointer;font-size:12px;transition:.15s"
                       :style="selectedSet.has(p.id) ? {borderColor:'var(--primary)',background:'var(--primary-dim)'} : {}"
                       @click="togglePlatform(p.id)">
                    <div style="width:16px;height:16px;border-radius:4px;border:2px solid var(--bd);display:flex;align-items:center;justify-content:center;font-size:10px;flex-shrink:0"
                         :style="selectedSet.has(p.id) ? {borderColor:'var(--primary)',background:'var(--primary)',color:'#000'} : {}">
                      {{ selectedSet.has(p.id) ? '✓' : '' }}
                    </div>
                    <span :style="{flex:1,color:selectedSet.has(p.id)?'var(--t1)':'var(--t2)'}">{{ p.name }}</span>
                    <span style="font-size:9px;color:var(--t3)">{{ p.dept }}</span>
                  </div>
                </div>
              </div>
              <div style="margin-top:10px;font-size:12px;color:var(--t2)">已选择 <strong style="color:var(--primary)">{{ store.selectedPlatforms.length }}</strong> 个平台</div>
            </div>
          </div>
        </div>

        <!-- Step 2: 文案生成 -->
        <div v-if="store.currentStep === 1">
          <!-- TXT 素材内容展示 -->
          <div v-if="store.fileManifest.txt_contents && Object.keys(store.fileManifest.txt_contents).length"
               style="margin-bottom:16px;padding:14px;background:var(--bg1);border:1px solid var(--primary);border-radius:8px">
            <div style="font-size:11px;color:var(--primary);font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px">
              📄 已从素材 TXT 提取内容（已自动填充到下方表单）
            </div>
            <div v-for="(content, fname) in store.fileManifest.txt_contents" :key="fname"
                 style="margin-bottom:8px">
              <div style="font-size:10px;color:var(--t3);margin-bottom:4px">{{ fname }}</div>
              <div style="font-size:12px;color:var(--t2);white-space:pre-wrap;max-height:120px;overflow-y:auto;line-height:1.6;padding:8px 10px;background:var(--bg3);border-radius:6px">{{ content }}</div>
            </div>
          </div>

          <div style="display:flex;gap:20px;flex-wrap:wrap">
            <div style="flex:1;min-width:280px">
              <h4 style="margin-bottom:12px;font-size:14px">文案输入</h4>
              <div style="display:flex;gap:14px;margin-bottom:14px">
                <div class="form-group" style="flex:1"><label>主角</label><input v-model="copyForm.protagonist" class="form-input" placeholder="主角名 / 描述" /></div>
                <div class="form-group" style="flex:1"><label>事件</label><input v-model="copyForm.event" class="form-input" placeholder="发生了什么事" /></div>
              </div>
              <div style="display:flex;gap:14px;margin-bottom:14px">
                <div class="form-group" style="flex:1"><label>生活照描述</label><input v-model="copyForm.photos" class="form-input" :placeholder="`${store.fileManifest.images.length}张图片`" /></div>
                <div class="form-group" style="flex:1"><label>视频内容</label><input v-model="copyForm.video_desc" class="form-input" :placeholder="`${store.fileManifest.videos.length}段视频`" /></div>
              </div>
              <div style="display:flex;gap:14px;margin-bottom:14px">
                <div class="form-group" style="flex:1"><label>文风</label>
                  <select v-model="copyForm.style" class="form-select">
                    <option>反转打脸风</option><option>搞笑玩梗风</option><option>麻辣吐槽风</option><option>深情共情风</option><option>悬念揭秘风</option>
                  </select>
                </div>
                <div class="form-group" style="flex:1"><label>作者</label><input v-model="copyForm.author" class="form-input" /></div>
              </div>
              <div class="form-group" style="margin-bottom:14px">
                <label>分类 <span v-if="store.dynamicCategories.length" style="font-size:10px;color:var(--t3)">(已从 {{ store.selectedPlatforms.length }} 个平台加载分类库)</span></label>
                <!-- 已选分类标签 -->
                <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">
                  <span v-for="c in copyForm.categories" :key="c"
                        style="padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;background:var(--primary-dim);color:var(--primary);border:1px solid var(--primary);display:flex;align-items:center;gap:4px"
                        @click="copyForm.categories.splice(copyForm.categories.indexOf(c), 1)">
                    {{ c }} <span style="font-size:13px">×</span>
                  </span>
                </div>
                <!-- 平台分类库（点击添加） -->
                <div v-if="store.dynamicCategories.length" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">
                  <span v-for="c in store.dynamicCategories.filter(c => !copyForm.categories.includes(c))" :key="c"
                        style="padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;background:var(--bg4);color:var(--t2);border:1px solid var(--bd);transition:.15s"
                        @click="copyForm.categories.push(c)">
                    + {{ c }}
                  </span>
                </div>
                <!-- 自定义输入 -->
                <div style="display:flex;gap:6px">
                  <input v-model="customCategory" class="form-input" style="flex:1" placeholder="输入分类后回车添加..."
                         @keydown.enter.prevent="addCustomCategory" />
                </div>
                <div v-if="store.dynamicCategories.length" class="form-hint">已合并 {{ store.selectedPlatforms.length }} 个平台的分类库（并集），发布时各平台只使用自己支持的分类</div>
              </div>
              <button class="btn btn-primary"
                      :disabled="store.isGenerating || !copyForm.protagonist.trim() || !copyForm.event.trim()"
                      @click="handleGenerateCopy">
                {{ store.isGenerating ? '⏳ 生成中...' : '🤖 AI 生成文案' }}
              </button>
              <span v-if="!copyForm.protagonist.trim() || !copyForm.event.trim()" style="font-size:11px;color:var(--orange);margin-left:8px">
                ← 请先填写主角和事件
              </span>
            </div>
            <div style="flex:1;min-width:280px">
              <h4 style="margin-bottom:12px;font-size:14px">生成结果</h4>
              <div v-if="store.isGenerating" style="display:flex;flex-direction:column;gap:10px">
                <div class="skeleton" style="height:36px" /><div class="skeleton" style="height:36px" /><div class="skeleton" style="height:160px" />
                <div style="text-align:center;font-size:12px;color:var(--primary)">🤖 AI 文案生成中…</div>
              </div>
              <template v-else>
                <div class="form-group" style="margin-bottom:10px"><label>标题</label><input v-model="editTitle" class="form-input" /></div>
                <div class="form-group" style="margin-bottom:10px"><label>关键词</label><input v-model="editKeywords" class="form-input" /></div>
                <div class="form-group" style="margin-bottom:10px"><label>正文</label><textarea v-model="editBody" class="form-textarea" rows="8" /></div>
                <div style="display:flex;gap:8px">
                  <button class="btn btn-green" :disabled="!editTitle" @click="handleConfirmCopy">✅ 确认文案，下一步 →</button>
                  <button class="btn btn-ghost" @click="handleGenerateCopy">🔄 重新生成</button>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- Step 3: 重命名 -->
        <div v-if="store.currentStep === 2">
          <h4 style="margin-bottom:12px;font-size:14px">图片批量重命名</h4>
          <p style="font-size:12px;color:var(--t2);margin-bottom:14px">标题关键词已自动填入作为文件名前缀，你可以修改。确认后图片将自动重命名并推进到下一步。</p>
          <div style="display:flex;gap:14px;margin-bottom:14px;flex-wrap:wrap">
            <div class="form-group" style="flex:2">
              <label>重命名前缀</label>
              <input v-model="prefix" class="form-input" />
              <div class="form-hint">自动从标题提取，可手动修改</div>
            </div>
            <div class="form-group" style="flex:1"><label>起始编号</label><input v-model.number="startNum" type="number" class="form-input" /></div>
            <div class="form-group" style="flex:1"><label>分隔符</label>
              <select v-model="separator" class="form-select"><option value="_">下划线 _</option><option value="-">短横线 -</option></select>
            </div>
          </div>
          <!-- 实时预览 -->
          <div v-if="renamePreviewLocal.length" class="panel" style="margin-bottom:14px">
            <div style="font-size:12px;font-weight:600;color:var(--t2);margin-bottom:10px">预览重命名结果</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px">
              <template v-for="r in renamePreviewLocal" :key="r.old">
                <div style="color:var(--t3)">{{ r.old }}</div>
                <div style="color:var(--green)">→ {{ r.new }}</div>
              </template>
            </div>
          </div>
          <div v-else style="padding:14px;background:var(--bg3);border-radius:8px;font-size:12px;color:var(--t3);margin-bottom:14px">
            请输入重命名前缀以预览结果
          </div>
          <button class="btn btn-green" :disabled="!prefix" @click="handleConfirmRename">✅ 确认重命名，下一步 →</button>
        </div>

        <!-- Step 4: 封面 -->
        <div v-if="store.currentStep === 3">
          <h4 style="margin-bottom:12px;font-size:14px">封面制作</h4>
          <p style="font-size:12px;color:var(--t2);margin-bottom:14px">系统将自动从素材图片中生成封面候选。请选择满意的封面，或重新生成。</p>
          <div style="display:flex;gap:14px;margin-bottom:14px;flex-wrap:wrap">
            <div class="form-group" style="flex:1;min-width:160px">
              <label>拼接方式</label>
              <select v-model="coverLayout" class="form-select">
                <option value="triple">三拼（3 张横向拼接）</option>
                <option value="single">单图（单张裁剪）</option>
                <option value="double">双拼</option>
                <option value="wide">宽屏横版</option>
                <option value="portrait">竖版</option>
              </select>
            </div>
            <div class="form-group" style="flex:1;min-width:160px">
              <label>封面尺寸</label>
              <select v-model="coverSize" class="form-select">
                <option value="1300x640">1300 × 640（标准横版）</option>
                <option value="800x450">800 × 450</option>
                <option value="900x1200">900 × 1200（竖版）</option>
              </select>
            </div>
            <div class="form-group" style="flex:0.5;min-width:100px">
              <label>头顶留白 %</label>
              <input v-model.number="coverHeadroom" type="number" class="form-input" min="0" max="50" />
            </div>
          </div>
          <button class="btn btn-primary" style="margin-bottom:14px" :disabled="isGeneratingCover" @click="handleGenerateCover">
            {{ isGeneratingCover ? '⏳ 生成中...' : '🖼️ 生成封面候选' }}
          </button>

          <!-- 封面候选展示 -->
          <div v-if="store.coverCandidates.length" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
            <div v-for="(c, i) in store.coverCandidates" :key="i"
                 style="border-radius:8px;overflow:hidden;cursor:pointer;position:relative;background:var(--bg3)"
                 :style="{border: store.selectedCover === i ? '2px solid var(--primary)' : '2px solid var(--bd)'}"
                 @click="store.selectedCover = i">
              <img :src="coverUrl(c)" :alt="'候选 ' + 'ABC'[i]"
                   style="width:100%;height:140px;object-fit:cover;display:block"
                   @error="($event.target as HTMLImageElement).style.display='none'" />
              <div style="padding:6px 8px;font-size:11px;color:var(--t2);text-align:center">
                候选 {{ 'ABC'[i] }} {{ i < 2 ? '('+coverLayout+')' : '(单图)' }}
              </div>
              <div v-if="store.selectedCover === i" style="position:absolute;top:6px;right:6px;background:var(--primary);color:#000;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:700">已选</div>
            </div>
          </div>
          <div style="margin-top:14px;display:flex;gap:8px">
            <button class="btn btn-green" :disabled="!store.coverCandidates.length" @click="handleConfirmCover">✅ 使用选中封面，下一步 →</button>
            <button class="btn btn-ghost" :disabled="isGeneratingCover" @click="handleGenerateCover">🔄 重新生成</button>
            <button class="btn btn-ghost" @click="openImagePicker">📁 手动选图</button>
          </div>

          <!-- 手动选图弹窗 — 从已上传素材中选择 -->
          <div v-if="showImagePicker" class="modal-overlay" @click.self="showImagePicker = false">
            <div class="modal" style="max-width:700px">
              <div class="modal-head">
                <div class="modal-title">📁 从素材图片中选择</div>
                <button style="background:none;border:none;color:var(--t2);font-size:24px;cursor:pointer" @click="showImagePicker = false">&times;</button>
              </div>
              <div class="modal-body">
                <p style="font-size:12px;color:var(--t2);margin-bottom:12px">选择图片后将使用选中的图片生成封面（选 1 张 = 单图，选 2 张 = 双拼，选 3 张 = 三拼）</p>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px">
                  <div v-for="img in store.fileManifest.images" :key="img"
                       style="border-radius:6px;overflow:hidden;cursor:pointer;position:relative"
                       :style="{border: pickerSelectedImages.includes(img) ? '2px solid var(--primary)' : '2px solid var(--bd)'}"
                       @click="togglePickerImage(img)">
                    <img :src="coverUrl(store.folderPath + '/' + img)" style="width:100%;height:80px;object-fit:cover;display:block"
                         @error="($event.target as HTMLImageElement).style.display='none'" />
                    <div style="font-size:9px;padding:2px 4px;color:var(--t3);text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ img }}</div>
                    <div v-if="pickerSelectedImages.includes(img)"
                         style="position:absolute;top:2px;right:2px;background:var(--primary);color:#000;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700">
                      {{ pickerSelectedImages.indexOf(img) + 1 }}
                    </div>
                  </div>
                </div>
              </div>
              <div class="modal-footer">
                <span style="font-size:12px;color:var(--t2);margin-right:auto">已选 {{ pickerSelectedImages.length }} 张</span>
                <button class="btn btn-ghost" @click="showImagePicker = false">取消</button>
                <button class="btn btn-primary" :disabled="!pickerSelectedImages.length" @click="confirmPickerImages">生成封面</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 5: 水印 -->
        <div v-if="store.currentStep === 4">
          <h4 style="margin-bottom:12px;font-size:14px">水印处理 <span style="font-size:12px;color:var(--t2);font-weight:400">— 根据已选平台自动匹配水印配置</span></h4>
          <div v-if="Object.keys(store.wmProgress).length === 0">
            <p style="font-size:12px;color:var(--t2);margin-bottom:14px">以下是各目标平台的水印方案，确认后系统将自动为图片和视频添加对应水印。</p>

            <!-- 水印方案预览卡片 -->
            <div v-if="wmPlan.length" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:16px">
              <div v-for="p in wmPlan" :key="p.platform_id" style="background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:14px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                  <span style="font-size:13px;font-weight:600">{{ p.name }}</span>
                  <span class="badge badge-primary" style="font-size:10px;padding:1px 6px">{{ p.has_video_wm ? '图片+视频' : '仅图片' }}</span>
                </div>
                <div style="font-size:11px;color:var(--t2);line-height:1.8">
                  <div style="display:flex;justify-content:space-between;padding:2px 0"><span>图片水印</span><span style="color:var(--t1)">{{ p.wm_image || '无' }}</span></div>
                  <div style="display:flex;justify-content:space-between;padding:2px 0"><span>水印位置</span><span style="color:var(--t1)">{{ p.wm_position || '右下角' }}</span></div>
                  <div style="display:flex;justify-content:space-between;padding:2px 0"><span>水印宽度</span><span style="color:var(--t1)">{{ p.wm_width || 264 }}px</span></div>
                </div>
              </div>
            </div>

            <div style="padding:12px 16px;background:var(--bg3);border-radius:8px;font-size:12px;color:var(--t2);margin-bottom:14px">
              💡 共 {{ store.selectedPlatforms.length }} 个平台 · 预计耗时 ~{{ Math.max(1, store.selectedPlatforms.length) }} 分钟
            </div>
            <button class="btn btn-green" @click="handleConfirmWatermark">✅ 确认水印方案，开始处理 →</button>
          </div>
          <div v-else style="display:flex;flex-direction:column;gap:10px">
            <div v-for="(info, pid) in store.wmProgress" :key="pid"
                 style="background:var(--bg3);border-radius:8px;padding:14px"
                 :style="{borderLeft: info.status==='done'?'3px solid var(--green)':info.status==='failed'?'3px solid var(--red)':info.status==='running'?'3px solid var(--primary)':'3px solid var(--bd)'}">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                <span style="font-weight:600">{{ info.name || `平台 ${pid}` }}</span>
                <span class="badge" :class="info.status==='done'?'badge-green':info.status==='failed'?'badge-red':'badge-primary'" style="font-size:10px">{{ info.status }}</span>
              </div>
              <div class="progress-bar" style="height:6px"><div class="progress-fill" :style="{width:info.progress+'%',background:info.status==='done'?'var(--green)':info.status==='failed'?'var(--red)':'var(--primary)'}" /></div>
            </div>
          </div>
        </div>

        <!-- Step 6: 发布 -->
        <div v-if="store.currentStep === 5">
          <h4 style="margin-bottom:12px;font-size:14px">上传 & 发布 <span style="font-size:12px;color:var(--t2);font-weight:400">— 多平台并行上传，切片完成后逐一发布</span></h4>
          <div v-if="Object.keys(store.publishStatus).length === 0" style="color:var(--t3);padding:20px;text-align:center">
            <div style="font-size:24px;margin-bottom:8px">⏳</div>
            等待水印处理完成后自动进入发布…
          </div>
          <div v-else style="display:flex;flex-direction:column;gap:10px">
            <div v-for="(info, pid) in store.publishStatus" :key="pid"
                 style="background:var(--bg3);border:1px solid var(--bd);border-radius:8px;padding:14px">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                <div style="display:flex;align-items:center;gap:10px">
                  <span class="badge" :class="info.status==='published'?'badge-green':info.status==='failed'?'badge-red':info.status==='publishing'?'badge-primary':'badge-plain'" style="font-size:10px;min-width:60px;justify-content:center">
                    {{ platformNameMap[pid] || `平台 ${pid}` }}
                  </span>
                  <span style="font-size:12px;font-weight:600" :style="{color: info.status==='published'?'var(--green)':info.status==='failed'?'var(--red)':info.status==='publishing'?'var(--primary)':'var(--t3)'}">
                    {{ info.status === 'published' ? '✅ 发布成功' : info.status === 'failed' ? '❌ 发布失败' : info.status === 'publishing' ? '⏳ 发布中...' : '排队等待' }}
                  </span>
                </div>
                <button v-if="info.status === 'failed'" class="btn btn-sm" style="color:var(--orange);border:1px solid var(--orange)"
                        @click="retryPlatform(Number(pid))">🔄 重试</button>
              </div>
              <div v-if="info.progress !== undefined && info.status === 'publishing'" class="progress-bar" style="height:6px;margin-bottom:6px">
                <div class="progress-fill" :style="{width:info.progress+'%',background:'var(--primary)'}" />
              </div>
              <div v-if="info.error" style="font-size:11px;color:var(--red);margin-top:4px;padding:6px 8px;background:rgba(239,83,80,.08);border-radius:4px">{{ info.error }}</div>
            </div>
          </div>
          <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
            <button class="btn btn-green btn-lg" :disabled="!canPublish" @click="handlePublish">🚀 一键发布所有已就绪平台</button>
            <span style="font-size:12px;color:var(--t2)">
              {{ Object.values(store.publishStatus).filter((s: any) => s.status === 'published').length }} / {{ Object.keys(store.publishStatus).length }} 个平台已发布
            </span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div style="padding:16px 24px;border-top:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;gap:8px">
          <button v-if="store.currentStep > 0" class="btn btn-ghost btn-sm" @click="handlePrev">← 上一步</button>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <span style="font-size:12px;color:var(--t3)">第 {{ store.currentStep + 1 }} 步 / 共 6 步</span>
          <button v-if="store.currentStep === 0" class="btn btn-primary btn-sm" :disabled="!canNext()" @click="handleNext">下一步 →</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wizard-wrap { background: var(--bg2); border: 1px solid var(--bd); border-radius: 14px; overflow: hidden; }

.upload-zone {
  border: 2px dashed var(--bd); border-radius: 10px; padding: 32px 20px;
  text-align: center; color: var(--t3); cursor: pointer; transition: .2s;
}
.upload-zone:hover { border-color: var(--primary); color: var(--t2); background: rgba(79,195,247,.03); }
.upload-zone.dragging { border-color: var(--primary); background: rgba(79,195,247,.08); border-style: solid; }
.upload-zone.uploaded { border-color: var(--green); border-style: solid; background: rgba(129,199,132,.04); text-align: left; padding: 16px 20px; }
.upload-icon { font-size: 36px; margin-bottom: 8px; }
.upload-hint { font-size: 14px; font-weight: 500; }
.upload-sub { font-size: 11px; color: var(--t3); margin-top: 4px; }
</style>
