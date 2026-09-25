import { apiClient } from "@/api/client"
import type { ChromatogramData, Run, RunDetail, Stage, StageType } from "@/types/api"

export interface CreateRunPayload {
  // Optional -- if omitted, the backend derives one from the filename(s) +
  // a UTC timestamp (app/naming.py's default_sample_id).
  sample_id?: string
  forward_read?: File
  reverse_read?: File
  config_overrides?: Record<string, number>
}

export async function createRun(payload: CreateRunPayload) {
  const form = new FormData()
  if (payload.sample_id) form.set("sample_id", payload.sample_id)
  if (payload.forward_read) form.set("forward_read", payload.forward_read)
  if (payload.reverse_read) form.set("reverse_read", payload.reverse_read)
  // Only touched fields belong here (DESIGN.md's New Analysis section) --
  // an untouched threshold is left out, never resubmitted at its current
  // value. The backend also treats an omitted field and `"{}"` differently
  // (null vs. an empty override map), so skip appending it entirely rather
  // than sending an empty object.
  if (payload.config_overrides && Object.keys(payload.config_overrides).length > 0) {
    form.set("config_overrides", JSON.stringify(payload.config_overrides))
  }

  const { data } = await apiClient.post<Run>("/runs", form, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return data
}

// Synchronous: runs every stage through to completion (or its stopping
// point) and returns the fully-resolved run in this same response --
// no polling needed to see the terminal state, including a biological
// QC stop (e.g. status "failed" from a sanity-check failure), which comes
// back as a normal 200, not an HTTP error.
export async function executeRun(runId: string) {
  const { data } = await apiClient.post<RunDetail>(`/runs/${runId}/execute`)
  return data
}

export interface RerunPayload {
  sample_id?: string
  config_overrides?: Record<string, number>
  auto_execute?: boolean
}

export async function rerunRun(runId: string, payload: RerunPayload) {
  const { data } = await apiClient.post<Run>(`/runs/${runId}/rerun`, payload)
  return data
}

export async function listRuns() {
  const { data } = await apiClient.get<Run[]>("/runs")
  return data
}

export async function getRun(runId: string) {
  const { data } = await apiClient.get<RunDetail>(`/runs/${runId}`)
  return data
}

export async function getStage(runId: string, stageType: StageType) {
  const { data } = await apiClient.get<Stage>(`/runs/${runId}/stages/${stageType}`)
  return data
}

export async function getChromatogram(runId: string, slot: "forward" | "reverse") {
  const { data } = await apiClient.get<ChromatogramData>(
    `/runs/${runId}/chromatogram/${slot}`
  )
  return data
}

// The report endpoint requires the same bearer auth as everything else, so
// a plain <a href> can't hit it directly -- fetch the bytes and hand the
// caller a Blob to save (see src/lib/download.ts).
export async function downloadReportBlob(runId: string) {
  const { data } = await apiClient.get(`/runs/${runId}/report`, {
    responseType: "blob",
  })
  return data as Blob
}

export async function renameRun(runId: string, sampleId: string) {
  const { data } = await apiClient.patch<Run>(`/runs/${runId}`, {
    sample_id: sampleId,
  })
  return data
}

export function getReportsExportUrl(runIds?: string[]) {
  if (!runIds || runIds.length === 0) return "/runs/reports/export"
  const params = new URLSearchParams()
  for (const id of runIds) params.append("run_ids", id)
  return `/runs/reports/export?${params.toString()}`
}
