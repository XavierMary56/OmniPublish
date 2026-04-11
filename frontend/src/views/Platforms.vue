<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/http'

const platforms = ref<any[]>([])
const deptFilter = ref('')
const showModal = ref(false)
const editId = ref<number|null>(null)
const catInput = ref('')

// 分页
const page = ref(1)
const pageSize = 12

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
          <span style="font-size:14px;font-weight:700">{{ p.name }}</span>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="badge" :class="p.is_active !== 0 ? 'badge-green' : 'badge-red'" style="font-size:10px;padding:1px 8px">{{ p.is_active !== 0 ? '启用' : '关闭' }}</span>
            <span class="badge badge-primary" style="font-size:10px;padding:1px 8px">{{ p.dept }}</span>
          </div>
        </div>
        <div style="font-size:12px;color:var(--t2);display:flex;flex-direction:column;gap:3px">
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">图片水印</span><span>{{ p.img_wm_file || '未配置' }}</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:var(--t3)">视频水印</span><span>{{ p.vid_wm_file || '未配置' }}</span></div>
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
              <input v-model="form.img_wm_file" class="form-input" placeholder="watermark/91video_logo.png" />
              <div style="font-size:10px;color:var(--t3);margin-top:2px">PNG 透明底，建议宽度 200~400px</div>
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
              <input v-model="form.vid_wm_file" class="form-input" placeholder="watermark/91video.mov" />
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
