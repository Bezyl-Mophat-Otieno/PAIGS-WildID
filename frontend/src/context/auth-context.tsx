import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { fetchCurrentUser, login as loginRequest } from "@/api/auth"
import {
  AUTH_UNAUTHORIZED_EVENT,
  clearAuthToken,
  getAuthToken,
  setAuthToken,
} from "@/api/client"
import type { User } from "@/types/api"

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (!getAuthToken()) {
      setIsLoading(false)
      return
    }
    fetchCurrentUser()
      .then(setUser)
      .catch(() => clearAuthToken())
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  async function login(email: string, password: string) {
    const { access_token } = await loginRequest(email, password)
    setAuthToken(access_token)
    // The login response omits `id`, which the admin all-runs view needs to
    // compare against a run's owner_id -- /auth/me is the source of truth.
    const me = await fetchCurrentUser()
    setUser(me)
  }

  function logout() {
    clearAuthToken()
    setUser(null)
  }

  const value = useMemo(
    () => ({ user, isLoading, login, logout }),
    [user, isLoading]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider")
  return ctx
}
