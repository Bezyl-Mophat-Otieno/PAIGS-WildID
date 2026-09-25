import type { ConfigItem, StageType } from "@/types/api"

// Display order/labels for grouping the 13 thresholds by pipeline stage --
// matches CLAUDE.md's stage sequence, not alphabetical or catalog order.
export const THRESHOLD_STAGE_ORDER: StageType[] = [
  "sanity_check",
  "trim",
  "orientation",
  "usability_check",
  "blast",
  "identification",
]

export const THRESHOLD_STAGE_LABELS: Partial<Record<StageType, string>> = {
  sanity_check: "Coarse Sanity Check",
  trim: "Trimming",
  orientation: "Orientation Detection",
  usability_check: "Usability Check",
  blast: "BLAST",
  identification: "Identification",
}

export function groupConfigByStage(items: ConfigItem[]) {
  const groups = new Map<StageType, ConfigItem[]>()
  for (const item of items) {
    const group = groups.get(item.stage_type) ?? []
    group.push(item)
    groups.set(item.stage_type, group)
  }

  return THRESHOLD_STAGE_ORDER.filter((stage) => groups.has(stage)).map((stage) => ({
    stage,
    label: THRESHOLD_STAGE_LABELS[stage] ?? stage,
    items: groups.get(stage)!,
  }))
}

// react-hook-form treats a dot in a field name as a nested-path separator,
// which would turn "sanity_check.max_n_proportion" into a nested object --
// use a flat, dot-free name for form state and map back to the real
// catalog key when building the submit payload.
export function toFieldName(key: string) {
  return key.replaceAll(".", "__")
}
