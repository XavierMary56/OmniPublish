/** OmniPublish — 流水线 Store */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http, { api } from '../api/http'
import { createTaskWs, type OmniWs } from '../api/ws'

export const usePipelineStore = defineStore('pipeline', () => {
  // 任务基础信息
  const taskId = ref<number | null>(null)
  const taskNo = ref('')
  const currentStep = ref(0)
  const status = ref('draft')

  // Step 1
  const folderPath = ref('')
  const selectedPlatforms = ref<number[]>([])
  const fileManifest = ref<{ images: string[]; videos: string[]; txts: string[] }>({ images: [], videos: [], txts: [] })
  const isUploading = ref(false)
  const uploadProgress = ref(0)

  // Step 2
  const copyResult = ref<{ title: string; keywords: string; body: string } | null>(null)
  const isGenerating = ref(false)
  const dynamicCategories = ref<string[]>([])

  // Step 3
  const renamePrefix = ref('')
  const renamePreview = ref<{ old: string; new: string }[]>([])

  // Step 4
  const coverCandidates = ref<string[]>([])
  const selectedCover = ref(0)

  // Step 5
  const wmProgress = ref<Record<number, { status: string; progress: number; name: string }>>({})

  // Step 6
  const publishStatus = ref<Record<number, { status: string; progress: number; error?: string }>>({})

  // WebSocket
  let ws: OmniWs | null = null

  /** 上传素材文件 */
  async function uploadFiles(files: File[]) {
    if (!files.length) return
    isUploading.value = true
    uploadProgress.value = 0

    const formData = new FormData()
    for (const f of files) {
      formData.append('files', f)
    }

    try {
      const res = await http.post('/pipeline/upload', formData, {
        headers: { 'Content-Type': undefined },
        onUploadProgress: (e) => {
          if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100)
        },
      })
      const data = res.data?.data ?? res.data
      folderPath.value = data.folder_path
      fileManifest.value = data.file_manifest
      uploadProgress.value = 100
      return data
    } finally {
      isUploading.value = false
    }
  }

  /** 创建任务 */
  async function createTask(folder: string, platforms: number[]) {
    const data = await api('POST', '/pipeline', { folder_path: folder, target_platforms: platforms })
    taskId.value = data.task_id
    taskNo.value = data.task_no
    fileManifest.value = data.file_manifest
    folderPath.value = folder
    selectedPlatforms.value = platforms
    currentStep.value = 1
    status.value = 'running'
    connectWs()
    return data
  }

  /** 加载已有任务 */
  async function loadTask(id: number) {
    const data = await api('GET', `/pipeline/${id}`)
    taskId.value = data.id
    taskNo.value = data.task_no
    currentStep.value = data.current_step
    status.value = data.status
    folderPath.value = data.folder_path
    selectedPlatforms.value = data.target_platforms || []
    fileManifest.value = data.file_manifest || { images: [], videos: [], txts: [] }
    if (data.confirmed_title) {
      copyResult.value = { title: data.confirmed_title, keywords: data.confirmed_keywords, body: data.confirmed_body }
    }
    renamePrefix.value = data.rename_prefix || ''
    coverCandidates.value = data.cover_candidates || []

    // 加载平台子任务状态
    for (const pt of (data.platform_tasks || [])) {
      wmProgress.value[pt.platform_id] = { status: pt.wm_status, progress: pt.wm_progress, name: pt.platform_name }
      publishStatus.value[pt.platform_id] = { status: pt.publish_status, progress: pt.upload_progress, error: pt.publish_error }
    }
    connectWs()
  }

  /** 加载动态分类 */
  async function loadCategories() {
    if (!taskId.value) return
    const data = await api('GET', `/pipeline/${taskId.value}/step/2/categories`)
    dynamicCategories.value = data.categories || []
  }

  /** AI 文案生成 */
  async function generateCopy(params: Record<string, any>) {
    if (!taskId.value) return
    isGenerating.value = true
    await api('POST', `/pipeline/${taskId.value}/step/2/generate`, params)
    // 结果通过 WebSocket 推送
  }

  /** 确认文案 */
  async function confirmCopy(title: string, keywords: string, body: string, author: string, categories: string[]) {
    if (!taskId.value) return
    await api('PUT', `/pipeline/${taskId.value}/step/2/confirm`, { title, keywords, body, author, categories })
    copyResult.value = { title, keywords, body }
    renamePrefix.value = title.slice(0, 20)
    currentStep.value = 2
  }

  /** 重命名预览 */
  async function previewRename(prefix: string, start: number, sep: string) {
    if (!taskId.value) return
    const data = await api('GET', `/pipeline/${taskId.value}/step/3/preview`, { prefix, start, separator: sep })
    renamePreview.value = data || []
  }

  /** 确认重命名 */
  async function confirmRename(prefix: string, start: number, digits: number, sep: string) {
    if (!taskId.value) return
    await api('PUT', `/pipeline/${taskId.value}/step/3/confirm`, { prefix, start, digits, separator: sep })
    currentStep.value = 3
  }

  /** 生成封面 */
  async function generateCover(layout: string, candidates: number) {
    if (!taskId.value) return
    await api('POST', `/pipeline/${taskId.value}/step/4/generate`, null, )
  }

  /** 确认封面 */
  async function confirmCover(index: number) {
    if (!taskId.value) return
    await api('PUT', `/pipeline/${taskId.value}/step/4/confirm`, { cover_index: index })
    selectedCover.value = index
    currentStep.value = 4
  }

  /** 确认水印方案 */
  async function confirmWatermark() {
    if (!taskId.value) return
    await api('PUT', `/pipeline/${taskId.value}/step/5/confirm`)
  }

  /** 发布 */
  async function publish(platformIds: number[] = []) {
    if (!taskId.value) return
    await api('POST', `/pipeline/${taskId.value}/step/6/publish`, { platform_ids: platformIds })
  }

  /** WebSocket 连接 */
  function connectWs() {
    if (!taskId.value || ws) return
    ws = createTaskWs(taskId.value)
    ws.on('step_changed', (data) => {
      if (data.to_step !== undefined) currentStep.value = data.to_step
      if (data.status === 'awaiting_confirm' && data.step === 1) {
        isGenerating.value = false
        // 重新加载任务获取文案结果
        if (taskId.value) loadTask(taskId.value)
      }
    })
    ws.on('platform_update', (data) => {
      if (data.wm_status) {
        wmProgress.value[data.platform_id] = {
          ...wmProgress.value[data.platform_id],
          status: data.wm_status,
          progress: data.wm_progress ?? wmProgress.value[data.platform_id]?.progress ?? 0,
        }
      }
      if (data.publish_status) {
        publishStatus.value[data.platform_id] = {
          ...publishStatus.value[data.platform_id],
          status: data.publish_status,
          error: data.publish_error,
        }
      }
    })
    ws.connect()
  }

  /** 清理 */
  function reset() {
    ws?.disconnect()
    ws = null
    taskId.value = null
    taskNo.value = ''
    currentStep.value = 0
    status.value = 'draft'
    folderPath.value = ''
    selectedPlatforms.value = []
    fileManifest.value = { images: [], videos: [], txts: [] }
    isUploading.value = false
    uploadProgress.value = 0
    copyResult.value = null
    isGenerating.value = false
    renamePreview.value = []
    coverCandidates.value = []
    wmProgress.value = {}
    publishStatus.value = {}
  }

  return {
    taskId, taskNo, currentStep, status,
    folderPath, selectedPlatforms, fileManifest, isUploading, uploadProgress,
    copyResult, isGenerating, dynamicCategories,
    renamePrefix, renamePreview,
    coverCandidates, selectedCover,
    wmProgress, publishStatus,
    uploadFiles, createTask, loadTask, loadCategories,
    generateCopy, confirmCopy,
    previewRename, confirmRename,
    generateCover, confirmCover,
    confirmWatermark, publish,
    reset,
  }
})
