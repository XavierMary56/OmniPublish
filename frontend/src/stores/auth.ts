/** OmniPublish — 用户认证 Store */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '../api/http'

interface User {
  id: number
  username: string
  display_name: string
  dept: string
  role: 'editor' | 'leader' | 'admin'
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem('token') || '')
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const res = await http.post('/auth/login', { username, password })
    const data = res.data?.data || res.data
    token.value = data.token
    user.value = data.user
    sessionStorage.setItem('token', data.token)
  }

  function logout() {
    token.value = ''
    user.value = null
    sessionStorage.removeItem('token')
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const res = await http.get('/auth/me')
      user.value = res.data?.data || res.data
    } catch {
      logout()
    }
  }

  return { token, user, isLoggedIn, isAdmin, login, logout, fetchMe }
})
