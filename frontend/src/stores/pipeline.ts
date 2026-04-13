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
  const fileManifest = ref<{ images: string[]; videos: string[]; txts: string[]; txt_contents?: Record<string, string> }>({ images: [], videos: [], txts: [] })
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

  // 分片配置（仅远程部署时使用）
  const CHUNK_SIZE = 10 * 1024 * 1024
  const LARGE_FILE_THRESHOLD = 500 * 1024 * 1024  // 500MB 以上才分片
  const CONCURRENT_UPLOADS = 4
  const folderId = ref('')

  /** 上传素材文件：优先直传，超大文件(>500MB)才分片 */
  async function uploadFiles(files: File[]) {
    if (!files.length) return
    isUploading.value = true
    uploadProgress.value = 0

    try {
      // 检查是否有超大文件需要分片
      const largeFiles = files.filter(f => f.size > LARGE_FILE_THRESHOLD)
      const normalFiles = files.filter(f => f.size <= LARGE_FILE_THRESHOLD)
      const totalSize = files.reduce((s, f) => s + f.size, 0)
      let uploadedSize = 0

      // 1. 所有普通文件（含视频）直传（本地部署很快）
      if (normalFiles.length > 0) {
        if (folderId.value) {
          await uploadWithDedup(normalFiles, folderId.value)
        } else {
          await uploadDirect(normalFiles)
        }
        uploadedSize = normalFiles.reduce((s, f) => s + f.size, 0)
        uploadProgress.value = totalSize > 0 ? Math.round((uploadedSize / totalSize) * 100) : 100
      }

      // 2. 超大文件(>500MB)分片上传
      for (const file of largeFiles) {
        await uploadSingleLargeFile(file, uploadedSize, totalSize)
        uploadedSize += file.size
      }

      uploadProgress.value = 100
      saveDraft()
    } finally {
      isUploading.value = false
    }
  }

  /** 通过本地路径直接引用素材（不上传，容器挂载目录） */
  async function useLocalPath(localPath: string) {
    isUploading.value = true
    uploadProgress.value = 0
    try {
      const data = await api('POST', '/pipeline/upload/local-path', { path: localPath })
      folderPath.value = data.folder_path
      folderId.value = data.folder_id || ''
      fileManifest.value = data.file_manifest
      uploadProgress.value = 100
      saveDraft()
    } finally {
      isUploading.value = false
    }
  }

  /** 去重上传（追加到已有文件夹，跳过同名同大小文件） */
  async function uploadWithDedup(files: File[], existingFolderId: string) {
    const formData = new FormData()
    for (const f of files) {
      formData.append('files', f)
    }
    const res = await http.post(`/pipeline/upload/dedup?folder_id=${existingFolderId}`, formData, {
      headers: { 'Content-Type': undefined },
      onUploadProgress: (e) => {
        if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100)
      },
    })
    const data = res.data?.data ?? res.data
    folderPath.value = data.folder_path
    folderId.value = data.folder_id
    fileManifest.value = data.file_manifest
    uploadProgress.value = 100
  }

  /** 直接上传（小文件） */
  async function uploadDirect(files: File[]) {
    const formData = new FormData()
    for (const f of files) {
      formData.append('files', f)
    }
    const res = await http.post('/pipeline/upload', formData, {
      headers: { 'Content-Type': undefined },
      onUploadProgress: (e) => {
        if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100)
      },
    })
    const data = res.data?.data ?? res.data
    folderPath.value = data.folder_path
    folderId.value = data.folder_id
    fileManifest.value = data.file_manifest
    uploadProgress.value = 100
  }

  /** 分片上传单个大文件（>50MB） */
  async function uploadSingleLargeFile(file: File, baseUploaded: number, totalSize: number) {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE)

    // 初始化分片会话
    const initRes = await http.post('/pipeline/upload/init', null, {
      params: {
        filename: file.name,
        total_size: file.size,
        total_chunks: totalChunks,
        folder_id: folderId.value || '',
      },
    })
    const init = initRes.data?.data ?? initRes.data
    const uploadId = init.upload_id
    if (!folderId.value) folderId.value = init.folder_id

    // 查询已上传的分片（断点续传）
    const existingChunks = new Set<number>(init.uploaded_chunks || [])
    let fileUploaded = 0

    // 计算已跳过的分片大小
    for (const idx of existingChunks) {
      fileUploaded += Math.min(CHUNK_SIZE, file.size - idx * CHUNK_SIZE)
    }

    // 构建待上传分片列表
    const pendingChunks: number[] = []
    for (let i = 0; i < totalChunks; i++) {
      if (!existingChunks.has(i)) pendingChunks.push(i)
    }

    // 并发上传分片（CONCURRENT_UPLOADS 个同时）
    const uploadChunk = async (chunkIdx: number) => {
      const start = chunkIdx * CHUNK_SIZE
      const end = Math.min(start + CHUNK_SIZE, file.size)
      const blob = file.slice(start, end)
      const chunkForm = new FormData()
      chunkForm.append('chunk', blob, `chunk_${chunkIdx}`)

      await http.post('/pipeline/upload/chunk', chunkForm, {
        headers: { 'Content-Type': undefined },
        params: { upload_id: uploadId, chunk_index: chunkIdx },
      })
      fileUploaded += (end - start)
      uploadProgress.value = Math.round(((baseUploaded + fileUploaded) / totalSize) * 100)
    }

    // 分批并发执行
    for (let batch = 0; batch < pendingChunks.length; batch += CONCURRENT_UPLOADS) {
      const batchChunks = pendingChunks.slice(batch, batch + CONCURRENT_UPLOADS)
      await Promise.all(batchChunks.map(uploadChunk))
    }

    // 合并分片
    const completeRes = await http.post('/pipeline/upload/complete', null, {
      params: { upload_id: uploadId },
    })
    const completeData = completeRes.data?.data ?? completeRes.data
    folderPath.value = completeData.folder_path || folderPath.value
    fileManifest.value = completeData.file_manifest || fileManifest.value
  }

  /** 保存草稿到 localStorage */
  function saveDraft() {
    const draft = {
      taskId: taskId.value,
      taskNo: taskNo.value,
      currentStep: currentStep.value,
      status: status.value,
      folderPath: folderPath.value,
      folderId: folderId.value,
      selectedPlatforms: selectedPlatforms.value,
      fileManifest: fileManifest.value,
      copyResult: copyResult.value,
      renamePrefix: renamePrefix.value,
      savedAt: Date.now(),
    }
    localStorage.setItem('omnipub_draft', JSON.stringify(draft))
  }

  /** 恢复草稿（并验证服务端素材是否还在） */
  async function loadDraft(): Promise<boolean> {
    const raw = localStorage.getItem('omnipub_draft')
    if (!raw) return false
    try {
      const draft = JSON.parse(raw)
      // 超过24小时的草稿丢弃
      if (Date.now() - draft.savedAt > 24 * 60 * 60 * 1000) {
        localStorage.removeItem('omnipub_draft')
        return false
      }
      if (draft.taskId) taskId.value = draft.taskId
      if (draft.taskNo) taskNo.value = draft.taskNo
      if (draft.currentStep !== undefined) currentStep.value = draft.currentStep
      if (draft.status) status.value = draft.status
      if (draft.folderPath) folderPath.value = draft.folderPath
      if (draft.folderId) folderId.value = draft.folderId
      if (draft.selectedPlatforms) selectedPlatforms.value = draft.selectedPlatforms
      if (draft.fileManifest) fileManifest.value = draft.fileManifest
      if (draft.copyResult) copyResult.value = draft.copyResult
      if (draft.renamePrefix) renamePrefix.value = draft.renamePrefix

      // 验证服务端任务是否还存在
      if (draft.taskId) {
        try {
          await api('GET', `/pipeline/${draft.taskId}`)
        } catch {
          // 任务不存在（404），清除 taskId 相关状态
          taskId.value = null
          taskNo.value = ''
          currentStep.value = 0
          status.value = 'draft'
        }
      }

      // 验证服务端素材是否还在
      if (draft.folderId) {
        try {
          const check = await api('GET', `/pipeline/upload/check/${draft.folderId}`)
          if (check.exists) {
            folderPath.value = check.folder_path
            fileManifest.value = check.file_manifest
            // 素材已就绪，进度设为 100%
            uploadProgress.value = 100
            isUploading.value = false
          } else {
            folderPath.value = ''
            folderId.value = ''
            fileManifest.value = { images: [], videos: [], txts: [] }
            uploadProgress.value = 0
          }
        } catch {
          // 检查失败，清除文件状态避免残留
          folderPath.value = ''
          folderId.value = ''
          fileManifest.value = { images: [], videos: [], txts: [] }
          uploadProgress.value = 0
        }
      } else if (draft.fileManifest) {
        // 有 fileManifest 但无 folderId（旧草稿格式），也标记为就绪
        const m = draft.fileManifest
        if (m.images?.length || m.videos?.length || m.txts?.length) {
          uploadProgress.value = 100
        }
      }
      return true
    } catch { return false }
  }

  /** 清除草稿 */
  function clearDraft() {
    localStorage.removeItem('omnipub_draft')
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
  let generatePollTimer: number | null = null

  async function generateCopy(params: Record<string, any>) {
    if (!taskId.value) return
    isGenerating.value = true
    await api('POST', `/pipeline/${taskId.value}/step/2/generate`, params)

    // 轮询备用方案（WebSocket 可能不稳定）
    if (generatePollTimer) clearInterval(generatePollTimer)
    generatePollTimer = window.setInterval(async () => {
      if (!taskId.value) return
      try {
        const data = await api('GET', `/pipeline/${taskId.value}`)
        const step2 = (data.steps || [])[1]
        if (step2 && (step2.status === 'awaiting_confirm' || step2.status === 'failed')) {
          isGenerating.value = false
          if (step2.status === 'awaiting_confirm' && step2.data) {
            copyResult.value = step2.data
          }
          // 重新加载完整任务数据
          await loadTask(taskId.value!)
          if (generatePollTimer) { clearInterval(generatePollTimer); generatePollTimer = null }
        }
      } catch {}
    }, 3000)
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
    folderId.value = ''
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
    clearDraft()
  }

  return {
    taskId, taskNo, currentStep, status,
    folderPath, folderId, selectedPlatforms, fileManifest, isUploading, uploadProgress,
    copyResult, isGenerating, dynamicCategories,
    renamePrefix, renamePreview,
    coverCandidates, selectedCover,
    wmProgress, publishStatus,
    uploadFiles, useLocalPath, createTask, loadTask, loadCategories,
    generateCopy, confirmCopy,
    previewRename, confirmRename,
    generateCover, confirmCover,
    confirmWatermark, publish,
    saveDraft, loadDraft, clearDraft,
    reset,
  }
})
