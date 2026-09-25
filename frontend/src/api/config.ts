import { apiClient } from "@/api/client"
import type { ConfigItem } from "@/types/api"

export async function listConfig() {
  const { data } = await apiClient.get<ConfigItem[]>("/config")
  return data
}

export async function updateConfig(id: string, value: number) {
  const { data } = await apiClient.put<ConfigItem>(`/config/${id}`, { value })
  return data
}
