import { apiClient } from "@/api/client"
import type { Role, User } from "@/types/api"

export interface InviteResponse {
  email: string
  role: Role
  temporary_password: string
}

export async function inviteUser(email: string, role: Role) {
  const { data } = await apiClient.post<InviteResponse>("/admin/invite", {
    email,
    role,
  })
  return data
}

export async function listUsers() {
  const { data } = await apiClient.get<User[]>("/admin/users")
  return data
}
