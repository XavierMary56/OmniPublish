<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import http, { api } from '../api/http'

const platforms = ref<any[]>([])
const deptFilter = ref('')
const showModal = ref(false)
const editId = ref<number|null>(null)
const catInput = ref('')

// 分页
const page = ref(1)
const pageSize = 15

const form = ref({
  name: '', dept: '', categories: [] as string[], is_active: 1,
  img_wm_file: '', img_wm_position: 'bottom-right', img_wm_width: 264, img_wm_opacity: 100,
  vid_wm_file: '', vid_wm_mode: 'corner-cycle', vid_wm_scale: 35, vid_wm_file2: '',
  api_base_url: '', project_code: '', layout_template: '',
})

const filtered = computed(() => {
  let list = platforms.value
  if (deptFilter.value) list = list.filter(p => p.dept.startsWith(deptFilter.value))
  return list
})

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))

const depts = computed(() => {
  const s = new Set(platforms.value.map((p: any) => p.dept.replace(/\d组$/, '')))
  return [...s].sort()
})

const activeCount = computed(() => platforms.value.filter(p => p.is_active !== 0).length)
const inactiveCount = computed(() => platforms.value.filter(p => p.is_active === 0).length)

async function load() {
  try { platforms.value = await api('GET', '/platforms') } catch {}
}

function openAdd() {
  editId.value = null
  form.value = {
    name: '', dept: '', categories: [], is_active: 1,
    img_wm_file: '', img_wm_position: 'bottom-right', img_wm_width: 264, img_wm_opacity: 100,
    vid_wm_file: '', vid_wm_mode: 'corner-cycle', vid_wm_scale: 35, vid_wm_file2: '',
    api_base_url: '', project_code: '', layout_template: '',
  }
  imgWmPreview.value = ''
  vidWmPreview.value = ''
  showModal.value = true
}

function openEdit(p: any) {
  editId.value = p.id
  form.value = {
    name: p.name, dept: p.dept, categories: [...(p.categories || [])], is_active: p.is_active ?? 1,
    img_wm_file: p.img_wm_file || '', img_wm_position: p.img_wm_position || 'bottom-right',
    img_wm_width: p.img_wm_width || 264, img_wm_opacity: p.img_wm_opacity ?? 100,
    vid_wm_file: p.vid_wm_file || '', vid_wm_mode: p.vid_wm_mode || 'corner-cycle',
    vid_wm_scale: p.vid_wm_scale || 35, vid_wm_file2: p.vid_wm_file2 || '',
    api_base_url: p.api_base_url || '', project_code: p.project_code || '',
    layout_template: p.layout_template || '',
  }
  initWmPreviews()
  showModal.value = true
}

async function save() {
  try {
    if (editId.value) await api('PUT', `/platforms/${editId.value}`, form.value)
    else await api('POST', '/platforms', form.value)
    showModal.value = false
    await load()
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
}

async function toggleActive(p: any) {
  try {
    await api('PUT', `/platforms/${p.id}`, { ...p, is_active: p.is_active ? 0 : 1 })
    await load()
  } catch {}
}

function addCat() {
  const c = catInput.value.trim()
  if (c && !form.value.categories.includes(c)) form.value.categories.push(c)
  catInput.value = ''
}
function removeCat(c: string) { form.value.categories = form.value.categories.filter(x => x !== c) }

// 水印文件上传
const imgWmPreview = ref('')
const vidWmPreview = ref('')
const isUploadingImgWm = ref(false)
const isUploadingVidWm = ref(false)

const wmUploadProgress = ref(0)

async function uploadWatermark(e: Event, type: 'img' | 'vid') {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  const file = input.files[0]

  // 文件大小检查
  const sizeMB = file.size / 1024 / 1024
  if (sizeMB > 200) {
    alert(`文件太大 (${sizeMB.toFixed(1)}MB)，水印文件建议不超过 200MB`)
    return
  }

  const formData = new FormData()
  formData.append('file', file)

  if (type === 'img') isUploadingImgWm.value = true
  else isUploadingVidWm.value = true
  wmUploadProgress.value = 0

  try {
    const pname = encodeURIComponent(form.value.name || '')
    const res = await http.post(`/platforms/upload-watermark?type=${type}&platform_name=${pname}`, formData, {
      headers: { 'Content-Type': undefined },
      timeout: 300000, // 5 分钟超时（大 MOV 文件）
      onUploadProgress: (e) => {
        if (e.total) wmUploadProgress.value = Math.round((e.loaded / e.total) * 100)
      },
    })
    const data = res.data?.data ?? res.data
    if (type === 'img') {
      form.value.img_wm_file = data.path
      imgWmPreview.value = data.preview_url || ''
      if (data.converted) {
        console.log('JPG 已自动转换为 PNG')
      }
    } else {
      form.value.vid_wm_file = data.path
      vidWmPreview.value = data.filename || file.name
    }
    wmUploadProgress.value = 100
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message || '未知错误'
    alert(`水印上传失败: ${detail}`)
    console.error('Watermark upload error:', err)
  } finally {
    if (type === 'img') isUploadingImgWm.value = false
    else isUploadingVidWm.value = false
    wmUploadProgress.value = 0
    try { input.value = '' } catch {}
  }
}

function replaceWatermark(type: 'img' | 'vid') {
  const input = document.createElement('input')
  input.type = 'file'
  // 视频水印放宽格式限制：MOV/MP4/PNG 都接受
  input.accept = type === 'img'
    ? 'image/png,image/jpeg,.png,.jpg,.jpeg'
    : '.mov,.mp4,.png,video/quicktime,video/mp4,image/png'
  input.style.display = 'none'
  document.body.appendChild(input) // 必须挂到 DOM 上，某些浏览器才能触发
  input.onchange = (e) => {
    uploadWatermark(e, type)
    document.body.removeChild(input) // 用完移除
  }
  // 用户取消选择时也清理
  input.addEventListener('cancel', () => {
    document.body.removeChild(input)
  })
  input.click()
}

// 编辑时预览已有水印
function initWmPreviews() {
  if (form.value.img_wm_file) {
    // 路径: /app/backend/uploads/watermarks/haijiao/1744638123_logo.png
    const wmIdx = form.value.img_wm_file.indexOf('watermarks/')
    imgWmPreview.value = wmIdx >= 0
      ? '/uploads/' + form.value.img_wm_file.substring(wmIdx)
      : '/uploads/watermarks/' + form.value.img_wm_file.split('/').pop()
  } else {
    imgWmPreview.value = ''
  }
  vidWmPreview.value = form.value.vid_wm_file ? form.value.vid_wm_file.split('/').pop() || '' : ''
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-size:16px;font-weight:700">业务线管理 <span style="font-size:13px;color:var(--t3);font-weight:400">({{ platforms.length }} 个平台)</span></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <select v-model="deptFilter" class="form-select" style="width:120px" @change="page=1">
          <option value="">全部部组</option>
          <option v-for="d in depts" :key="d" :value="d">{{ d }}</option>
        </select>
        <button class="btn btn-primary" @click="openAdd">＋ 新增业务线</button>
      </div>
    </div>

    <p style="font-size:12px;color:var(--t2);margin-bottom:16px">每个业务线的水印、分类库、发布 API、排版模板等参数在此配置。发帖流水线会自动读取对应配置。</p>

    <!-- Stats -->
    <div style="display:flex;gap:10px;margin-bottom:16px">
      <div style="padding:8px 14px;background:var(--bg3);border-radius:8px;font-size:12px">
        <span style="color:var(--t3)">启用</span> <strong style="color:var(--green)">{{ activeCount }}</strong>
      </div>
      <div style="padding:8px 14px;background:var(--bg3);border-radius:8px;font-size:12px">
        <span style="color:var(--t3)">关闭</span> <strong style="color:var(--red)">{{ inactiveCount }}</strong>
      </div>
    </div>

    <!-- Config Cards Grid -->
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px">
      <div v-for="p in paged" :key="p.id"
           class="config-card"
           :style="{opacity: p.is_active === 0 ? 0.5 : 1}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:10px;color:var(--t3);background:var(--bg4);padding:1px 6px;border-radius:4px">ID:{{ p.id }}</span>
            <span style="font-size:14px;font-weight:700">{{ p.name }}</span>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="badge" :class="p.is_active !== 0 ? 'badge-green' : 'badge-red'" style="font-size:10px;padding:1px 8px">{{ p.is_active !== 0 ? '启用' : '关闭' }}</span>
            <span class="badge badge-primary" style="font-size:10px;padding:1px 8px">{{ p.dept }}</span>
          </div>
        </div>
        <div style="font-size:12px;color:var(--t2);display:flex;flex-direction:column;gap:3px">
          <div style="display:flex;justify-content:space-between;align-items:center"><span style="color:var(--t3)">图片水印</span>
            <span v-if="p.img_wm_file" style="display:flex;align-items:center;gap:4px">
              <img :src="p.img_wm_file.indexOf('watermarks/') >= 0 ? '/uploads/' + p.img_wm_file.substring(p.img_wm_file.indexOf('watermarks/')) : '/uploads/watermarks/' + p.img_wm_file.split('/').pop()" style="height:18px;width:auto;border-radius:2px;background:#333" @error="($event.target as HTMLImageElement).style.display='none'" />
              <span style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ p.img_wm_file.split('/').pop() }}</span>
            </span>
            <span v-else style="color:var(--t3)">未配置</span>
          </div>
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">视频水印</span>
            <span v-if="p.vid_wm_file">{{ p.vid_wm_file.split('/').pop() }}</span>
            <span v-else style="color:var(--t3)">未配置</span>
          </div>
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">水印模式</span><span>{{ p.vid_wm_mode === 'corner-cycle' ? '四角轮转' : p.vid_wm_mode === 'fixed' ? '固定位置' : p.vid_wm_mode === 'diagonal' ? '双水印对角' : p.vid_wm_mode || '—' }}</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">分类库</span><span>{{ (p.categories||[]).length }} 个</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">API 入口</span><span style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ p.api_base_url || '未配置' }}</span></div>
        </div>
        <div v-if="(p.categories||[]).length" style="display:flex;gap:3px;flex-wrap:wrap;margin-top:8px">
          <span v-for="c in (p.categories||[]).slice(0,6)" :key="c" style="font-size:9px;padding:2px 6px;background:var(--bg4);color:var(--t2);border-radius:3px">{{ c }}</span>
          <span v-if="(p.categories||[]).length > 6" style="font-size:9px;padding:2px 6px;color:var(--t3)">+{{ (p.categories||[]).length - 6 }}</span>
        </div>
        <div style="margin-top:12px;display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" @click="openEdit(p)">编辑</button>
          <button class="btn btn-sm" :style="{color: p.is_active !== 0 ? 'var(--red)' : 'var(--green)', border: '1px solid', borderColor: p.is_active !== 0 ? 'var(--red)' : 'var(--green)', background: 'transparent', padding: '4px 10px', fontSize: '11px', borderRadius: '6px', cursor: 'pointer'}"
                  @click="toggleActive(p)">{{ p.is_active !== 0 ? '关闭' : '启用' }}</button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" style="display:flex;align-items:center;justify-content:center;gap:8px;margin-top:20px">
      <button class="btn btn-ghost btn-sm" :disabled="page <= 1" @click="page--">← 上一页</button>
      <template v-for="n in totalPages" :key="n">
        <button class="btn btn-sm"
                :style="{padding:'4px 10px',fontSize:'12px',borderRadius:'6px',cursor:'pointer',
                  background: n===page ? 'var(--primary)' : 'transparent',
                  color: n===page ? '#000' : 'var(--t2)',
                  border: n===page ? 'none' : '1px solid var(--bd)'}"
                @click="page=n">{{ n }}</button>
      </template>
      <button class="btn btn-ghost btn-sm" :disabled="page >= totalPages" @click="page++">下一页 →</button>
      <span style="font-size:11px;color:var(--t3);margin-left:8px">共 {{ filtered.length }} 个 · 第 {{ page }}/{{ totalPages }} 页</span>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal" style="max-width:860px">
        <div class="modal-head">
          <div class="modal-title">{{ editId ? '编辑' : '新增' }}业务线</div>
          <button style="background:none;border:none;color:var(--t2);font-size:24px;cursor:pointer" @click="showModal=false">&times;</button>
        </div>
        <div class="modal-body" style="max-height:70vh;overflow-y:auto">
          <!-- 基础信息 -->
          <div style="display:flex;gap:14px;margin-bottom:14px">
            <div class="form-group" style="flex:1"><label>业务线名称 *</label><input v-model="form.name" class="form-input" placeholder="如：91视频web" /></div>
            <div class="form-group" style="flex:1"><label>负责部门</label><input v-model="form.dept" class="form-input" placeholder="如：1部4组" /></div>
            <div class="form-group" style="flex:0.6">
              <label>状态</label>
              <select v-model.number="form.is_active" class="form-select">
                <option :value="1">启用</option>
                <option :value="0">关闭</option>
              </select>
            </div>
          </div>

          <!-- 分类库 -->
          <div class="section-divider">分类库</div>
          <div class="form-group" style="margin-bottom:14px">
            <label>分类列表（留空表示该平台不需要分类）</label>
            <div style="display:flex;flex-wrap:wrap;gap:4px;padding:8px 10px;background:var(--bg3);border:1px solid var(--bd);border-radius:7px;min-height:40px;align-items:center">
              <span v-for="c in form.categories" :key="c" class="cat-tag">
                {{ c }} <span style="cursor:pointer;opacity:.7;margin-left:2px" @click="removeCat(c)">&times;</span>
              </span>
              <input v-model="catInput" style="border:none;background:transparent;color:var(--t1);font-size:12px;outline:none;flex:1;min-width:100px" placeholder="输入分类名后回车添加…" @keydown.enter.prevent="addCat" />
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:10px;color:var(--t3)">
              <span>共 {{ form.categories.length }} 个分类 · 回车添加，×删除</span>
            </div>
          </div>

          <!-- 图片水印 -->
          <div class="section-divider">图片水印配置</div>
          <div style="display:flex;gap:14px;margin-bottom:14px;flex-wrap:wrap">
            <div class="form-group" style="flex:2;min-width:200px">
              <label>水印文件 (PNG)</label>
              <!-- 已上传：显示预览 + 替换按钮 -->
              <div v-if="form.img_wm_file" style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border:1px solid var(--green);border-radius:8px">
                <img v-if="imgWmPreview" :src="imgWmPreview" style="height:40px;width:auto;max-width:120px;object-fit:contain;background:repeating-conic-gradient(#333 0% 25%, #444 0% 50%) 50% / 10px 10px;border-radius:4px" />
                <span v-else style="font-size:20px">🖼️</span>
                <div style="flex:1;overflow:hidden">
                  <div style="font-size:12px;color:var(--t1);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ form.img_wm_file.split('/').pop() }}</div>
                  <div v-if="imgWmPreview" style="font-size:10px;color:var(--t3)">PNG 透明底</div>
                </div>
                <button class="btn btn-ghost btn-sm" @click="replaceWatermark('img')" style="white-space:nowrap">替换</button>
              </div>
              <!-- 未上传：显示上传区域 -->
              <div v-else style="display:flex;flex-direction:column;align-items:center;gap:4px;padding:16px;border:2px dashed var(--bd);border-radius:8px;cursor:pointer;transition:.2s"
                   @click="replaceWatermark('img')"
                   @mouseenter="($event.currentTarget as HTMLElement).style.borderColor='var(--primary)'"
                   @mouseleave="($event.currentTarget as HTMLElement).style.borderColor='var(--bd)'">
                <span v-if="isUploadingImgWm" style="font-size:13px;color:var(--primary)">⏳ 上传中 {{ wmUploadProgress }}%</span>
                <template v-else>
                  <span style="font-size:20px">🖼️</span>
                  <span style="font-size:12px;color:var(--primary)">点击上传图片水印 (PNG/JPG)</span>
                </template>
              </div>
              <div style="font-size:10px;color:var(--t3);margin-top:2px">支持 PNG/JPG，JPG 会自动转 PNG 透明底，建议宽度 200~400px</div>
            </div>
            <div class="form-group" style="flex:1"><label>水印位置</label>
              <select v-model="form.img_wm_position" class="form-select">
                <option value="bottom-right">右下角</option>
                <option value="bottom-left">左下角</option>
                <option value="top-right">右上角</option>
                <option value="top-left">左上角</option>
              </select>
            </div>
            <div class="form-group" style="flex:0.7"><label>水印宽度 (px)</label><input v-model.number="form.img_wm_width" type="number" class="form-input" /></div>
            <div class="form-group" style="flex:0.7"><label>不透明度 (%)</label><input v-model.number="form.img_wm_opacity" type="number" class="form-input" min="0" max="100" /></div>
          </div>

          <!-- 视频水印 -->
          <div class="section-divider">视频水印配置</div>
          <div style="display:flex;gap:14px;margin-bottom:14px;flex-wrap:wrap">
            <div class="form-group" style="flex:2;min-width:200px">
              <label>水印文件 (.mov/.png)</label>
              <!-- 已上传 -->
              <div v-if="form.vid_wm_file" style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border:1px solid var(--green);border-radius:8px">
                <span style="font-size:20px">🎬</span>
                <div style="flex:1;overflow:hidden">
                  <div style="font-size:12px;color:var(--t1);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ vidWmPreview || form.vid_wm_file.split('/').pop() }}</div>
                  <div style="font-size:10px;color:var(--t3)">MOV 透明通道 或 PNG 静态水印</div>
                </div>
                <button class="btn btn-ghost btn-sm" @click="replaceWatermark('vid')" style="white-space:nowrap">替换</button>
              </div>
              <!-- 未上传 -->
              <div v-else style="display:flex;flex-direction:column;align-items:center;gap:4px;padding:16px;border:2px dashed var(--bd);border-radius:8px;cursor:pointer;transition:.2s"
                   @click="replaceWatermark('vid')"
                   @mouseenter="($event.currentTarget as HTMLElement).style.borderColor='var(--primary)'"
                   @mouseleave="($event.currentTarget as HTMLElement).style.borderColor='var(--bd)'">
                <span v-if="isUploadingVidWm" style="font-size:13px;color:var(--primary)">⏳ 上传中 {{ wmUploadProgress }}%</span>
                <template v-else>
                  <span style="font-size:20px">🎬</span>
                  <span style="font-size:12px;color:var(--primary)">点击上传视频水印 (MOV/PNG)</span>
                </template>
              </div>
              <div style="font-size:10px;color:var(--t3);margin-top:2px">MOV 透明通道 或 PNG 静态水印</div>
            </div>
            <div class="form-group" style="flex:1"><label>水印模式</label>
              <select v-model="form.vid_wm_mode" class="form-select">
                <option value="corner-cycle">四角轮转</option>
                <option value="fixed">固定位置</option>
                <option value="diagonal">双水印对角</option>
              </select>
            </div>
            <div class="form-group" style="flex:0.7"><label>缩放比例 (%)</label><input v-model.number="form.vid_wm_scale" type="number" class="form-input" /></div>
          </div>

          <!-- 发布配置 -->
          <div class="section-divider">发布配置</div>
          <div style="display:flex;gap:14px;margin-bottom:14px">
            <div class="form-group" style="flex:1"><label>API 入口</label><input v-model="form.api_base_url" class="form-input" placeholder="https://xxx.xxx/api.php" /></div>
            <div class="form-group" style="flex:1"><label>项目代码</label><input v-model="form.project_code" class="form-input" placeholder="项目标识符" /></div>
          </div>
          <div class="form-group" style="margin-bottom:14px">
            <label>排版模板</label>
            <textarea v-model="form.layout_template" class="form-textarea" rows="4" style="font-family:monospace;font-size:11px" placeholder="正文&#10;图片1-3&#10;## 小标题&#10;正文&#10;视频" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showModal=false">取消</button>
          <button class="btn btn-primary" @click="save">保存业务线</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-card {
  background: var(--bg2); border: 1px solid var(--bd); border-radius: 10px; padding: 18px; transition: .15s;
}
.config-card:hover { border-color: var(--primary); }

.section-divider {
  font-size: 13px; font-weight: 600; color: var(--t2);
  margin: 16px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--bd);
}

.cat-tag {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 3px 8px; background: var(--primary-dim); color: var(--primary);
  border-radius: 4px; font-size: 11px; font-weight: 500;
}

.modal-overlay {
  display: flex; position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 200;
  align-items: flex-start; justify-content: center; padding: 40px 20px; overflow-y: auto;
}
.modal {
  background: var(--bg2); border: 1px solid var(--bd); border-radius: 14px; width: 100%; max-width: 800px; overflow: hidden;
}
.modal-head {
  padding: 18px 24px; border-bottom: 1px solid var(--bd);
  display: flex; align-items: center; justify-content: space-between;
}
.modal-title { font-size: 17px; font-weight: 700; }
.modal-body { padding: 24px; }
.modal-footer {
  padding: 16px 24px; border-top: 1px solid var(--bd);
  display: flex; justify-content: flex-end; gap: 8px;
}
</style>
