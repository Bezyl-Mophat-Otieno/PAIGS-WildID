import { apiClient } from "@/api/client"
import type { PublishReferenceDatabaseResult, ReferenceDatabaseVersion } from "@/types/api"

export async function listReferenceDatabaseVersions() {
  const { data } = await apiClient.get<ReferenceDatabaseVersion[]>(
    "/reference-database/versions"
  )
  return data
}

// 404 with `{detail: "No reference database has been published yet."}` is
// the real "nothing published" state here, not an error -- callers should
// treat that 404 as an empty result, not surface it generically.
export async function getActiveReferenceDatabase() {
  const { data } = await apiClient.get<ReferenceDatabaseVersion>(
    "/reference-database/active"
  )
  return data
}

// Publishing always immediately activates the new version and deactivates
// every other one -- there's no separate "activate" step and no staging
// state. The response omits is_active/published_at; re-fetch /active or
// /versions after a successful publish to show those.
export async function publishReferenceDatabase(fasta: File, version: string) {
  const form = new FormData()
  form.set("fasta", fasta)
  form.set("version", version)

  const { data } = await apiClient.post<PublishReferenceDatabaseResult>(
    "/reference-database/publish",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  )
  return data
}
