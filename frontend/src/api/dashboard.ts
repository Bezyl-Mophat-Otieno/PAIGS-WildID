import { apiClient } from "@/api/client"
import type { DashboardStats } from "@/types/api"

export async function fetchDashboardStats() {
  const { data } = await apiClient.get<DashboardStats>("/dashboard/stats")
  return data
}
