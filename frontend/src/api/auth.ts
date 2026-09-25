import { apiClient } from "@/api/client"
import type { LoginResponse, User } from "@/types/api"

export async function login(email: string, password: string) {
  const form = new URLSearchParams()
  form.set("username", email)
  form.set("password", password)

  const { data } = await apiClient.post<LoginResponse>("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  })
  return data
}

export async function fetchCurrentUser() {
  const { data } = await apiClient.get<User>("/auth/me")
  return data
}
