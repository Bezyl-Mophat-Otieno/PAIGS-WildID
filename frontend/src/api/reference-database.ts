import { apiClient } from "@/api/client"
import type {
  PublishReferenceDatabaseResult,
  ReferenceDatabaseDraft,
  ReferenceDatabaseVersion,
} from "@/types/api"

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

export async function listSuggestedTaxa() {
  const { data } = await apiClient.get<string[]>("/reference-database/suggested-taxa")
  return data
}

export async function listReferenceDrafts() {
  const { data } = await apiClient.get<ReferenceDatabaseDraft[]>("/reference-database/drafts")
  return data
}

export async function createReferenceDraft(payload: {
  taxon: string
  marker?: string
  // All four omitted means "use the current bold_fetch.* global default"
  // (see GET /config) -- not a value hardcoded here.
  max_records_per_species?: number
  min_sequence_length?: number
  max_n_proportion?: number
  require_species_level?: string
}) {
  const { data } = await apiClient.post<ReferenceDatabaseDraft>(
    "/reference-database/drafts",
    payload
  )
  return data
}

// The human review/approve step -- the only thing that turns a draft
// into something Runs can actually search against.
export async function publishReferenceDraft(draftId: string, version: string) {
  const { data } = await apiClient.post<PublishReferenceDatabaseResult>(
    `/reference-database/drafts/${draftId}/publish`,
    { version }
  )
  return data
}

export async function discardReferenceDraft(draftId: string) {
  const { data } = await apiClient.post<ReferenceDatabaseDraft>(
    `/reference-database/drafts/${draftId}/discard`
  )
  return data
}
