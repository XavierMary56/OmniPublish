<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('admin')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.response?.data?.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-box">
      <h2>OmniPublish</h2>
      <p class="sub">V2.0 · 全链路发帖工作台</p>

      <form @submit.prevent="handleLogin">
        <div class="form-group" style="margin-bottom:14px">
          <label>用户名</label>
          <input v-model="username" class="form-input" placeholder="请输入用户名" autofocus />
        </div>
        <div class="form-group" style="margin-bottom:14px">
          <label>密码</label>
          <input v-model="password" type="password" class="form-input" placeholder="请输入密码" />
        </div>
        <div v-if="error" style="color:var(--red);font-size:12px;margin-bottom:10px">{{ error }}</div>
        <button class="btn btn-primary btn-lg" style="width:100%;justify-content:center" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>
      <p style="margin-top:14px;font-size:11px;color:var(--t3)">忘记密码？请联系管理员</p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: var(--bg0);
}
.login-box {
  background: var(--bg2); border: 1px solid var(--bd); border-radius: 14px;
  padding: 40px; width: 380px; text-align: center;
}
.login-box h2 { font-size: 22px; font-weight: 800; color: var(--primary); margin-bottom: 4px; }
.login-box .sub { font-size: 12px; color: var(--t3); margin-bottom: 28px; }
.login-box .form-group { text-align: left; }
</style>
