/** OmniPublish — Axios HTTP 封装 + 拦截器 */
import axios from 'axios'
import router from '../router'
import { useAuthStore } from '../stores/auth'

const http = axios.create({
  baseURL: '/api',
  timeout: 600000, // 10 分钟超时（支持大文件上传）
  maxContentLength: Infinity,
  maxBodyLength: Infinity,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截：自动附加 Token
http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// 响应拦截：处理 401
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      router.push('/login')
    }
    return Promise.reject(err)
  },
)

export default http

/** 通用 API 调用 */
export async function api<T = any>(method: string, url: string, data?: any): Promise<T> {
  const res = method === 'GET'
    ? await http.get(url, { params: data })
    : method === 'DELETE'
    ? await http.delete(url, { data })
    : method === 'PUT'
    ? await http.put(url, data)
    : await http.post(url, data)
  return res.data?.data ?? res.data
}
