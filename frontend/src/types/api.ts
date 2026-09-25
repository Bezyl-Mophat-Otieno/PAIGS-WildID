// Shapes mirror the backend's Pydantic schemas (see ../../CLAUDE.md and
// ../../DESIGN.md for the full contract). Kept hand-written and minimal --
// widen a shape as a screen actually needs more of it, rather than
// front-loading fields nothing reads yet.

export type Role = "admin" | "analyst"

export interface User {
  id: string
  email: string
  role: Role
  is_active: boolean
  created_at: string
  invited_by_id: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: "bearer"
  role: Role
  email: string
}

export type StageType =
  | "import"
  | "format_check"
  | "ab1_extraction"
  | "sanity_check"
  | "trim"
  | "orientation"
  | "consensus"
  | "usability_check"
  | "fasta"
  | "blast"
  | "identification"
  | "report"

export type StageStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"

export interface Stage {
  run_id: string
  stage_type: StageType
  status: StageStatus
  input_ref: string | null
  output: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  stage_metadata: Record<string, unknown> | null
}

// GET /runs/{id} and the POST /execute response return this lighter shape
// per stage (no output/input_ref/metadata) -- enough to drive a stepper.
// Full detail per stage comes from GET /runs/{id}/stages/{type} (`Stage` above).
export interface StageSummary {
  stage_type: StageType
  status: StageStatus
  attempt_number: number
  started_at: string | null
  completed_at: string | null
}

export type RunStatus = "in_progress" | "paused" | "completed" | "failed"

export interface Run {
  id: string
  sample_id: string
  owner_id: string
  original_filenames: string[]
  created_at: string
  current_stage: StageType
  status: RunStatus
  rerun_of: string | null
  config_overrides: Record<string, number> | null
}

// Returned by GET /runs/{id} and POST /runs/{id}/execute -- a Run plus its
// per-stage progress.
export interface RunDetail extends Run {
  stages: StageSummary[]
}

// GET /config never exposes bounds (they're server-only, enforced via a 422
// on submit) -- so there's no min/max here. value_type says how to treat
// `value`/`default` (int vs float) without hardcoding it per key.
export interface ConfigItem {
  id: string
  key: string
  stage_type: StageType
  param_name: string
  label: string
  description: string
  value: number
  value_type: "int" | "float"
  default: number
  updated_at: string
}

export interface DashboardStats {
  total_samples_processed: number
  identification_rate: number | null
  qc_pass_rate: number | null
  pending_review_count: number
  species_breakdown: { species: string; count: number }[]
  quality_score_histogram: { bucket: string; count: number }[]
}

export interface ReferenceDatabaseVersion {
  version: string
  published_at: string
  published_by_id: string
  sequence_count: number
}

export interface ChromatogramData {
  channel_order: string[]
  trace: Record<string, number[]>
  peak_locations: number[]
  base_calls: string[]
}
