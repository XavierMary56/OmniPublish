<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/http'

interface Account {
  id: number; platform_id: number; platform_name: string
  api_url: string; api_url_masked: string; username: string; username_masked: string
  login_status: string; last_login_at: string; last_error: string; dept: string
}

const accounts = ref<Account[]>([])
const platforms = ref<any[]>([])
const showModal = ref(false)
const editId = ref<number | null>(null)
const form = ref({ platform_id: 0, username: '', password: '' })
const showPassword = ref(false)
const isLogging = ref<number | null>(null)

async function load() {
  try { accounts.value = await api('GET', '/accounts') } catch {}
  try { platforms.value = await api('GET', '/platforms') } catch {}
}

// 未绑定账号的平台列表
const unboundPlatforms = computed(() => {
  const boundIds = new Set(accounts.value.map(a => a.platform_id))
  return platforms.value.filter(p => !boundIds.has(p.id))
})

function openAdd() {
  editId.value = null
  form.value = { platform_id: 0, username: '', password: '' }
  showPassword.value = false
  showModal.value = true
}

function openEdit(a: Account) {
  editId.value = a.id
  form.value = { platform_id: a.platform_id, username: a.username, password: '' }
  showPassword.value = false
  showModal.value = true
}

async function save() {
  try {
    if (editId.value) {
      const data: any = {}
      if (form.value.username) data.username = form.value.username
      if (form.value.password) data.password = form.value.password
      await api('PUT', `/accounts/${editId.value}`, data)
    } else {
      if (!form.value.platform_id) { alert('请选择平台'); return }
      await api('POST', '/accounts', form.value)
    }
    showModal.value = false
    await load()
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
}

async function remove(id: number) {
  if (!confirm('确定删除此账号？')) return
  try {
    await api('DELETE', `/accounts/${id}`)
    await load()
  } catch (e: any) { alert(e.response?.data?.detail || '删除失败') }
}

async function testLogin(id: number) {
  isLogging.value = id
  try {
    await api('POST', `/accounts/${id}/login`)
    await load()
  } catch (e: any) {
    alert('登录失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    isLogging.value = null
  }
}

function statusClass(s: string) {
  return s === 'active' ? 'badge-green' : s === 'expired' ? 'badge-red' : 'badge-plain'
}
function statusLabel(s: string) {
  return s === 'active' ? '已登录' : s === 'expired' ? '已过期' : '未激活'
}

onMounted(load)
</script>

<template>
<div>
  <div class="section-header">
    <div class="section-title">账号管理</div>
    <button class="btn btn-primary" @click="openAdd">＋ 添加账号</button>
  </div>
  <p style="font-size:12px;color:var(--t2);margin-bottom:16px">各平台后台登录凭据管理，发布时自动使用对应账号。</p>

  <!-- 空状态 -->
  <div v-if="!accounts.length" style="padding:40px;text-align:center;color:var(--t3)">
    <div style="font-size:32px;margin-bottom:10px">🔑</div>
    <div style="font-size:14px;margin-bottom:6px">暂无账号</div>
    <div style="font-size:12px">点击上方「添加账号」绑定平台登录凭据</div>
  </div>

  <!-- 账号列表 -->
  <div v-else class="table-wrap">
    <table>
      <thead><tr>
        <th>ID</th><th>平台</th><th>入口 URL</th><th>用户名</th><th>登录状态</th><th>上次登录</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="a in accounts" :key="a.id">
          <td style="color:var(--t3)">{{ a.id }}</td>
          <td class="t1">{{ a.platform_name }}</td>
          <td style="color:var(--t3);font-size:12px">{{ a.api_url_masked || a.api_url }}</td>
          <td>{{ a.username_masked || a.username }}</td>
          <td>
            <span class="badge" :class="statusClass(a.login_status)">{{ statusLabel(a.login_status) }}</span>
            <span v-if="a.login_status === 'expired'" style="font-size:10px;color:var(--red);margin-left:6px">⚠️ 发帖前需重新登录</span>
          </td>
          <td style="white-space:nowrap">{{ a.last_login_at || '—' }}</td>
          <td>
            <div style="display:flex;gap:6px">
              <button class="btn btn-sm" :class="a.login_status === 'expired' ? 'action-orange' : 'btn-ghost'"
                      :disabled="isLogging === a.id"
                      @click="testLogin(a.id)">
                {{ isLogging === a.id ? '⏳...' : '重新登录' }}
              </button>
              <button class="btn btn-sm btn-ghost" @click="openEdit(a)">编辑</button>
              <button class="btn btn-sm" style="color:var(--red);border:1px solid rgba(239,83,80,.3);background:transparent" @click="remove(a.id)">删除</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 添加/编辑 Modal -->
  <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
    <div class="modal" style="max-width:500px">
      <div class="modal-head">
        <div class="modal-title">{{ editId ? '编辑账号' : '添加账号' }}</div>
        <button style="background:none;border:none;color:var(--t2);font-size:24px;cursor:pointer" @click="showModal = false">&times;</button>
      </div>
      <div class="modal-body">
        <!-- 选择平台（新增时） -->
        <div v-if="!editId" class="form-group" style="margin-bottom:14px">
          <label>选择平台 *</label>
          <select v-model.number="form.platform_id" class="form-select">
            <option :value="0" disabled>请选择平台</option>
            <option v-for="p in unboundPlatforms" :key="p.id" :value="p.id">{{ p.name }} ({{ p.dept }})</option>
          </select>
          <div v-if="!unboundPlatforms.length" style="font-size:11px;color:var(--orange);margin-top:4px">所有平台已绑定账号</div>
        </div>

        <!-- API 地址（只读，来自业务线配置） -->
        <div v-if="!editId && form.platform_id" class="form-group" style="margin-bottom:14px">
          <label>API 入口 URL <span style="font-size:10px;color:var(--t3)">(来自业务线配置，如需修改请到「业务线管理」)</span></label>
          <div style="padding:8px 11px;background:var(--bg4);border:1px solid var(--bd);border-radius:7px;font-size:12px;color:var(--t3)">
            {{ platforms.find(p => p.id === form.platform_id)?.api_base_url || '未配置' }}
          </div>
        </div>

        <div class="form-group" style="margin-bottom:14px">
          <label>用户名</label>
          <input v-model="form.username" class="form-input" placeholder="登录用户名" />
        </div>

        <div class="form-group" style="margin-bottom:14px">
          <label>密码 {{ editId ? '(留空则不修改)' : '' }}</label>
          <div style="display:flex;gap:8px">
            <input v-model="form.password" :type="showPassword ? 'text' : 'password'" class="form-input" style="flex:1"
                   :placeholder="editId ? '留空不修改' : '登录密码'" />
            <button class="btn btn-ghost btn-sm" @click="showPassword = !showPassword" style="white-space:nowrap">
              {{ showPassword ? '🙈 隐藏' : '👁️ 显示' }}
            </button>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" @click="showModal = false">取消</button>
        <button class="btn btn-primary" @click="save">{{ editId ? '保存修改' : '添加账号' }}</button>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.action-orange { color: var(--orange) !important; border: 1px solid var(--orange) !important; background: transparent !important; }
</style>
