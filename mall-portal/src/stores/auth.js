import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAuth, setAuth, removeAuth } from '@/utils/auth'
import { logout as logoutApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(getAuth().user || null)

  const isLogin = computed(() => !!user.value)

  function loginSuccess(userVal) {
    user.value = userVal
    setAuth({ user: userVal })
  }

  function clearAuth() {
    user.value = null
    removeAuth()
  }

  async function logout() {
    try { await logoutApi() } catch {}
    clearAuth()
  }

  return { user, isLogin, loginSuccess, logout, clearAuth }
})
