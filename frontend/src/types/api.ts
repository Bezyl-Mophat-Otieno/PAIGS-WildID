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

// GET /runs/{id} and POST /execute return this lighter shape per stage (no
// output/input_ref/metadata) -- enough to drive a stepper. Full detail per
// stage comes from GET /runs/{id}/stages/{type} (`Stage` below). Neither
// carries a run_id -- it's implicit in the URL you fetched.
export interface StageSummary {
  stage_type: StageType
  status: StageStatus
  attempt_number: number
  started_at: string | null
  completed_at: string | null
}

// `output`/`stage_metadata` are genuinely untyped on the backend (Optional[Any]
// in StageDetail -- a loose JSON column, no per-stage response schema) --
// narrow with an `as` cast at each panel using the shapes below, hand-modeled
// from the actual pipeline code in app/orchestration/execute.py and
// app/pipeline/*.py.
export interface Stage extends StageSummary {
  input_ref: null
  output: unknown
  stage_metadata: unknown
}

export type ReadSlotKey = "forward" | "reverse"

export interface ImportOutput {
  original_filenames: string[]
  stored_filenames: string[]
  slots: ReadSlotKey[]
}

export interface FormatCheckResult {
  filename: string
  valid: boolean
  reason: string | null
}
export type FormatCheckOutput = Partial<Record<ReadSlotKey, FormatCheckResult>>

export interface Ab1ExtractionResult {
  raw_sequence: string
  raw_length: number
  quality_scores: number[]
}
export type Ab1ExtractionOutput =
  | Partial<Record<ReadSlotKey, Ab1ExtractionResult>>
  | { error: string }

export interface SanityCheckResult {
  n_proportion: number
  raw_length: number
  status: "PASS" | "FAIL"
  reason: string | null
}
export type SanityCheckOutput = Partial<Record<ReadSlotKey, SanityCheckResult>>
export interface SanityCheckMetadata {
  single_read_reason: "single_file_provided" | "qc_failure" | null
  thresholds: { max_n_proportion: number; min_raw_length: number }
}

export interface TrimResult {
  trimmed_sequence: string
  trimmed_length: number
  trim_start: number
  trim_end: number
  trim_params: { quality_threshold: number; min_window_size: number }
}
export type TrimOutput = Partial<Record<ReadSlotKey, TrimResult>>
export interface TrimMetadata {
  thresholds: { quality_threshold: number; min_window_size: number }
}

export interface OrientationOutput {
  orientation: "as_is" | "reverse_read_reverse_complemented" | "no_overlap_found"
  alignment_score: number | null
  overlap_length: number | null
  identity: number | null
  label_orientation_mismatch: boolean | null
}
export interface OrientationMetadata {
  thresholds: { min_overlap_length: number; min_identity: number }
}

export interface ResolvedPosition {
  position: number
  forward_base: string
  forward_quality: number
  reverse_base: string
  reverse_quality: number
  resolved_base: string
  resolved_quality: number
  changed: boolean
  method: "agreement" | "ambiguity_consistency" | "quality_tiebreak"
}
export interface ConsensusOutput {
  consensus_sequence: string
  consensus_length: number
  ambiguous_positions: number[]
  quality_scores: number[]
  resolved_positions: ResolvedPosition[]
}

export interface UsabilityCheckOutput {
  final_length: number
  mean_quality: number
  ambiguous_positions: number
  status: "PASS" | "FAIL"
  reason: string | null
}
export interface UsabilityCheckMetadata {
  thresholds: {
    min_length: number
    min_mean_quality: number
    max_ambiguous_proportion: number
  }
}

export interface FastaOutput {
  sequence_id: string
  sequence_length: number
  fasta_content: string
}

export interface BlastHit {
  rank: number
  species: string
  identity: number
  coverage: number
  evalue: number
  bit_score: number
  accession: string
}
export type BlastOutput =
  | { hits: BlastHit[]; database_version: string; query_length: number }
  | { error: string }
export interface BlastMetadata {
  thresholds: { max_hits: number }
}

export interface IdentificationOutput {
  candidate_species: string | null
  identity: number | null
  coverage: number | null
  status: "PASS" | "AMBIGUOUS" | "REVIEW REQUIRED"
  reason: string | null
  thresholds_applied: {
    min_identity_pct: number
    min_coverage_pct: number
    ambiguous_margin_pct: number
  }
  taxonomic_consistency_checked: boolean
}

export interface ReportOutput {
  report_path: string
}

export interface ErrorOutput {
  error: string
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

// species_breakdown is sorted (count desc, species asc) but NOT capped --
// the frontend does its own top-N + "Other" collapsing. All 5
// quality_score_histogram buckets are always present, even at count 0.
export interface DashboardStats {
  total_samples_processed: number
  identification_rate: number | null
  qc_pass_rate: number | null
  pending_review_count: number
  species_breakdown: { species: string; count: number }[]
  quality_score_histogram: { label: string; count: number }[]
}

// GET /reference-database/versions and /active both return this shape.
// There is no `published_by` field anywhere in the backend today -- no
// user-lookup join is possible here (unlike RunRead's owner_id).
export interface ReferenceDatabaseVersion {
  version: string
  fasta_path: string
  db_prefix: string
  sequence_count: number
  is_active: boolean
  published_at: string
}

// POST /publish's success response is a narrower shape than the version
// list/active read -- no is_active or published_at, so a fresh
// GET /reference-database/active is needed to show either afterward.
export interface PublishReferenceDatabaseResult {
  version: string
  fasta_path: string
  db_prefix: string
  sequence_count: number
}

export interface ChromatogramData {
  channel_order: string[]
  trace: Record<string, number[]>
  peak_locations: number[]
  base_calls: string[]
}
