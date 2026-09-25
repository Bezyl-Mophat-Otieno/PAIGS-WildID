import { apiClient } from "@/api/client"
import type { Role, User } from "@/types/api"

export interface InviteResponse {
  user: User
  temporary_password: string
  email: {
    to: string
    subject: string
    delivered: boolean
    note: string
  }
}

// role is optional server-side (defaults to "analyst"), but this app
// always sends an explicit choice from the invite form.
export async function inviteUser(email: string, role: Role) {
  const { data } = await apiClient.post<InviteResponse>("/admin/invite", {
    email,
    role,
  })
  return data
}

// Unfiltered and unpaginated -- includes the calling admin and the seeded
// default admin, sorted oldest-created first.
export async function listUsers() {
  const { data } = await apiClient.get<User[]>("/admin/users")
  return data
}
