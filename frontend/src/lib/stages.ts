import type { StageSummary, StageType } from "@/types/api"

// The pipeline's fixed 12-stage sequence (CLAUDE.md's Run/Stage model) --
// the stepper always renders all 12, regardless of how far a run got.
export const STAGE_ORDER: StageType[] = [
  "import",
  "format_check",
  "ab1_extraction",
  "sanity_check",
  "trim",
  "orientation",
  "consensus",
  "usability_check",
  "fasta",
  "blast",
  "identification",
  "report",
]

export const STAGE_LABELS: Record<StageType, string> = {
  import: "Import",
  format_check: "Format Validity",
  ab1_extraction: "AB1 Extraction",
  sanity_check: "Sanity Check",
  trim: "Trimming",
  orientation: "Orientation",
  consensus: "Consensus",
  usability_check: "Usability Check",
  fasta: "FASTA",
  blast: "BLAST",
  identification: "Identification",
  report: "Report",
}

export const READ_SLOT_LABELS = {
  forward: "Forward Read",
  reverse: "Reverse Read",
} as const

// A stage with no row yet (still "pending") has nothing to fetch --
// GET /runs/{id}/stages/{type} would just 404. Shared by Run Detail and
// Rerun, both of which need to know before calling useStage.
export function stageHasRun(stages: StageSummary[], stageType: StageType) {
  const summary = stages.find((s) => s.stage_type === stageType)
  return Boolean(summary && summary.status !== "pending")
}
