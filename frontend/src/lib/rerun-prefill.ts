import type { EffectiveThresholdRow } from "@/lib/effective-thresholds"
import type { ConfigItem } from "@/types/api"

// DESIGN.md's Rerun screen: prefill from the source Run's own effective
// thresholds, not current global defaults -- global config can drift
// between when the source ran and when someone reruns it. A threshold the
// source never reached (its stage didn't run) has no effective value to
// reuse, so it falls back to the current catalog default -- there's
// nothing else to prefill it with.
export function mergeSourceThresholds(
  catalog: ConfigItem[],
  sourceRows: EffectiveThresholdRow[]
): ConfigItem[] {
  const byKey = new Map(sourceRows.map((row) => [row.key, row.value]))
  return catalog.map((item) =>
    byKey.has(item.key) ? { ...item, value: byKey.get(item.key)! } : item
  )
}

export interface ThresholdDiffRow {
  key: string
  label: string
  sourceValue: number | undefined
  rerunValue: number | undefined
  changed: boolean
}

// DESIGN.md: "the side-by-side view should highlight exactly which of the
// 13 keys actually differ between them, not just list each Run's values in
// isolation."
export function buildThresholdDiff(
  catalog: ConfigItem[],
  sourceRows: EffectiveThresholdRow[],
  rerunRows: EffectiveThresholdRow[]
): ThresholdDiffRow[] {
  const sourceByKey = new Map(sourceRows.map((row) => [row.key, row.value]))
  const rerunByKey = new Map(rerunRows.map((row) => [row.key, row.value]))

  return catalog.map((item) => {
    const sourceValue = sourceByKey.get(item.key)
    const rerunValue = rerunByKey.get(item.key)
    return {
      key: item.key,
      label: item.label,
      sourceValue,
      rerunValue,
      changed: sourceValue !== undefined && rerunValue !== undefined && sourceValue !== rerunValue,
    }
  })
}
