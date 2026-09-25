import { apiClient } from "@/api/client"
import type { ReferenceDatabaseVersion } from "@/types/api"

export async function listReferenceDatabaseVersions() {
  const { data } = await apiClient.get<ReferenceDatabaseVersion[]>(
    "/reference-database/versions"
  )
  return data
}

export async function getActiveReferenceDatabase() {
  const { data } = await apiClient.get<ReferenceDatabaseVersion>(
    "/reference-database/active"
  )
  return data
}

export async function publishReferenceDatabase(fasta: File, version: string) {
  const form = new FormData()
  form.set("fasta", fasta)
  form.set("version", version)

  const { data } = await apiClient.post<ReferenceDatabaseVersion>(
    "/reference-database/publish",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  )
  return data
}
