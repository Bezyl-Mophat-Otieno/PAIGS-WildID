import axios from "axios"

// No shared /api prefix on the backend -- routers mount at root
// (/auth, /runs, /config, ...). Vite's dev proxy (vite.config.ts) forwards
// those paths to the backend; in production VITE_API_BASE_URL points at it
// directly.
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "",
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
