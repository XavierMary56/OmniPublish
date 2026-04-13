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
const coverLayout = ref('triple')

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

function triggerUpload() {
  // 默认选文件夹（webkitdirectory）
  folderInput.value?.click()
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

async function handleGenerateCover() {
  await store.generateCover(coverLayout.value, 3)
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
                   @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
                   @click="triggerUpload()">
                <input ref="fileInput" type="file" multiple accept="image/*,video/*,.txt" style="display:none" @change="onFileSelect" />
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
                      <span style="font-size:11px;color:var(--t3);margin-left:auto">点击可追加文件</span>
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
                  <div class="upload-hint">拖入素材文件夹 或 点击选择文件</div>
                  <div class="upload-sub">支持：图片（JPG/PNG/WebP）、视频（MP4/MOV）、文案（TXT）</div>
                </template>
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
          <div style="display:flex;gap:20px;flex-wrap:wrap">
            <div style="flex:1;min-width:280px">
              <h4 style="margin-bottom:12px;font-size:14px">文案输入</h4>
              <div style="display:flex;gap:14px;margin-bottom:14px">
                <div class="form-group" style="flex:1"><label>主角</label><input v-model="copyForm.protagonist" class="form-input" placeholder="主角名" /></div>
                <div class="form-group" style="flex:1"><label>事件</label><input v-model="copyForm.event" class="form-input" placeholder="发生了什么" /></div>
              </div>
              <div style="display:flex;gap:14px;margin-bottom:14px">
                <div class="form-group" style="flex:1"><label>文风</label>
                  <select v-model="copyForm.style" class="form-select">
                    <option>反转打脸风</option><option>搞笑玩梗风</option><option>麻辣吐槽风</option><option>深情共情风</option><option>悬念揭秘风</option>
                  </select>
                </div>
                <div class="form-group" style="flex:1"><label>作者</label><input v-model="copyForm.author" class="form-input" /></div>
              </div>
              <div v-if="store.dynamicCategories.length" class="form-group" style="margin-bottom:14px">
                <label>分类（已从选中平台加载 {{ store.dynamicCategories.length }} 个）</label>
                <div style="display:flex;flex-wrap:wrap;gap:4px">
                  <span v-for="c in store.dynamicCategories" :key="c"
                        style="padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;transition:.15s"
                        :style="copyForm.categories.includes(c) ? {background:'var(--primary-dim)',color:'var(--primary)',border:'1px solid var(--primary)'} : {background:'var(--bg4)',color:'var(--t2)',border:'1px solid var(--bd)'}"
                        @click="copyForm.categories.includes(c) ? copyForm.categories.splice(copyForm.categories.indexOf(c),1) : copyForm.categories.push(c)">
                    {{ c }}
                  </span>
                </div>
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
          <div style="display:flex;gap:14px;margin-bottom:14px">
            <div class="form-group"><label>拼接方式</label>
              <select v-model="coverLayout" class="form-select"><option value="triple">三拼</option><option value="single">单图</option><option value="double">双拼</option><option value="wide">宽屏</option><option value="portrait">竖版</option></select>
            </div>
          </div>
          <button class="btn btn-primary" style="margin-bottom:14px" @click="handleGenerateCover">🖼️ 生成封面候选</button>
          <div v-if="store.coverCandidates.length" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
            <div v-for="(c, i) in store.coverCandidates" :key="i"
                 style="border-radius:8px;overflow:hidden;cursor:pointer;position:relative;height:120px;display:flex;align-items:center;justify-content:center;background:var(--bg3);color:var(--t3);font-size:12px"
                 :style="{border: store.selectedCover === i ? '2px solid var(--primary)' : '2px solid var(--bd)'}"
                 @click="store.selectedCover = i">
              候选 {{ 'ABC'[i] }}
              <div v-if="store.selectedCover === i" style="position:absolute;top:6px;right:6px;background:var(--primary);color:#000;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:700">已选</div>
            </div>
          </div>
          <div style="margin-top:14px;display:flex;gap:8px">
            <button class="btn btn-green" :disabled="!store.coverCandidates.length" @click="handleConfirmCover">✅ 使用选中封面，下一步 →</button>
          </div>
        </div>

        <!-- Step 5: 水印 -->
        <div v-if="store.currentStep === 4">
          <h4 style="margin-bottom:12px;font-size:14px">水印处理</h4>
          <div v-if="Object.keys(store.wmProgress).length === 0">
            <p style="font-size:12px;color:var(--t2);margin-bottom:14px">确认后系统将为各平台并行添加水印。</p>
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
          <h4 style="margin-bottom:12px;font-size:14px">上传 & 发布</h4>
          <div v-if="Object.keys(store.publishStatus).length === 0" style="color:var(--t3);padding:20px">等待水印处理完成…</div>
          <div v-else style="display:flex;flex-direction:column;gap:10px">
            <div v-for="(info, pid) in store.publishStatus" :key="pid"
                 style="background:var(--bg3);border-radius:8px;padding:14px"
                 :style="{borderLeft: info.status==='published'?'3px solid var(--green)':info.status==='failed'?'3px solid var(--red)':'3px solid var(--bd)'}">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <span style="font-weight:600">平台 {{ pid }}</span>
                <span class="badge" :class="info.status==='published'?'badge-green':info.status==='failed'?'badge-red':'badge-primary'" style="font-size:10px">{{ info.status }}</span>
              </div>
              <div v-if="info.error" style="font-size:11px;color:var(--red);margin-top:6px">{{ info.error }}</div>
            </div>
          </div>
          <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
            <button class="btn btn-green btn-lg" :disabled="!canPublish" @click="handlePublish">🚀 一键发布所有已就绪平台</button>
            <span v-if="!canPublish" style="font-size:12px;color:var(--t3)">等待平台就绪中…</span>
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
