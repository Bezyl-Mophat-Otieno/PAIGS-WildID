import axios from "axios"

// The backend itself has no /api prefix (routers mount at root: /auth,
// /runs, /config, ...), but several of those names collide with this SPA's
// own routes (e.g. /runs/:id is both a page and a backend path) -- `/api`
// here is a dev-only namespace that Vite's proxy strips before forwarding
// (see vite.config.ts), so a hard navigation to a frontend route never gets
// intercepted as an API call. In production VITE_API_BASE_URL points at the
// deployed backend's real origin directly, and this default is unused.
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api",
})

const TOKEN_STORAGE_KEY = "wildid.access_token"

// Kept in memory first, sessionStorage second -- sessionStorage survives a
// page reload (so the app can restore the session via GET /auth/me) but not
// a closed tab, and is preferred over localStorage to limit XSS exposure
// (DESIGN.md's Auth section).
let inMemoryToken: string | null = sessionStorage.getItem(TOKEN_STORAGE_KEY)

export function getAuthToken() {
  return inMemoryToken
}

export function setAuthToken(token: string) {
  inMemoryToken = token
  sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearAuthToken() {
  inMemoryToken = null
  sessionStorage.removeItem(TOKEN_STORAGE_KEY)
}

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const AUTH_UNAUTHORIZED_EVENT = "wildid:unauthorized"

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAuthToken()
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
    }
    return Promise.reject(error)
  }
)
