import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

const request = axios.create({
  baseURL: '/portal-api',
  timeout: 10000,
  withCredentials: true
})

function trimValues(obj) {
  if (typeof obj === 'string') return obj.trim()
  if (Array.isArray(obj)) return obj.map(trimValues)
  if (obj !== null && typeof obj === 'object' && !(obj instanceof FormData)) {
    for (const key in obj) { obj[key] = trimValues(obj[key]) }
  }
  return obj
}

request.interceptors.request.use(config => {
  if (config.data) config.data = trimValues(config.data)
  if (config.params) config.params = trimValues(config.params)
  return config
})

request.interceptors.response.use(
  res => {
    if (res.config.responseType === 'blob') return res
    if (res.data.code !== 20000) {
      if (res.data.code === 40100) {
        useAuthStore().clearAuth()
        router.push('/login')
      }
      return Promise.reject(res.data)
    }
    return res.data
  },
  err => {
    ElMessage.error('网络错误')
    return Promise.reject(err)
  }
)

export default request
