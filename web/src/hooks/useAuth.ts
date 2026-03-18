import { useCallback, useEffect, useState } from 'react'
import {
  getMe,
  login as loginApi,
  logout as logoutApi,
} from '../api/endpoints'
import type { User } from '../types'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMe()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await loginApi(username, password)
    setUser(res.data)
  }, [])

  const logout = useCallback(async () => {
    await logoutApi()
    setUser(null)
  }, [])

  return { user, loading, login, logout }
}
