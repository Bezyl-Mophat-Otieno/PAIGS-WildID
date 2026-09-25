import type { Stage, StageType } from "@/types/api"

export interface EffectiveThresholdRow {
  key: string
  stageType: StageType
  paramName: string
  value: number
}

// Mirrors what the backend's own report generation assembles internally
// (app/orchestration/execute.py's `thresholds_used`, embedded in the PDF but
// never itself stored as a Stage's output) -- reconstructed here from each
// stage's own record instead, since Run Detail and Rerun both need it and
// neither can read the PDF's internal dict.
const THRESHOLDS_FROM_METADATA: StageType[] = [
  "sanity_check",
  "trim",
  "orientation",
  "usability_check",
  "blast",
]

export function buildEffectiveThresholds(
  stagesByType: Partial<Record<StageType, Stage>>
): EffectiveThresholdRow[] {
  const rows: EffectiveThresholdRow[] = []

  for (const stageType of THRESHOLDS_FROM_METADATA) {
    const metadata = stagesByType[stageType]?.stage_metadata as
      | { thresholds?: Record<string, number> }
      | null
      | undefined
    if (!metadata?.thresholds) continue
    for (const [paramName, value] of Object.entries(metadata.thresholds)) {
      rows.push({ key: `${stageType}.${paramName}`, stageType, paramName, value })
    }
  }

  // identification never gets a stage_metadata.thresholds entry -- its
  // thresholds live inside its own output instead.
  const identificationOutput = stagesByType.identification?.output as
    | { thresholds_applied?: Record<string, number> }
    | null
    | undefined
  if (identificationOutput?.thresholds_applied) {
    for (const [paramName, value] of Object.entries(identificationOutput.thresholds_applied)) {
      rows.push({ key: `identification.${paramName}`, stageType: "identification", paramName, value })
    }
  }

  return rows
}
