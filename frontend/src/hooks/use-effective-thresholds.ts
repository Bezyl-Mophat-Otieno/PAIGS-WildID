import { useQueries } from "@tanstack/react-query"
import { getStage } from "@/api/runs"
import { stageQueryKey } from "@/hooks/use-stage"
import { buildEffectiveThresholds } from "@/lib/effective-thresholds"
import { stageHasRun } from "@/lib/stages"
import type { Stage, StageSummary, StageType } from "@/types/api"

const RELEVANT_STAGES: StageType[] = [
  "sanity_check",
  "trim",
  "orientation",
  "usability_check",
  "blast",
  "identification",
]

// Shared by Run Detail's "Thresholds used" panel and the Rerun screen's
// prefill/diff -- reads the same six stages' own records rather than
// duplicating the reconstruction per screen (DESIGN.md's explicit ask).
export function useEffectiveThresholds(runId: string, stages: StageSummary[]) {
  const queries = useQueries({
    queries: RELEVANT_STAGES.map((stageType) => ({
      queryKey: stageQueryKey(runId, stageType),
      queryFn: () => getStage(runId, stageType),
      enabled: stageHasRun(stages, stageType),
    })),
  })

  const stagesByType: Partial<Record<StageType, Stage>> = {}
  queries.forEach((query, index) => {
    if (query.data) stagesByType[RELEVANT_STAGES[index]] = query.data
  })

  return {
    rows: buildEffectiveThresholds(stagesByType),
    isLoading: queries.some((q) => q.isLoading),
  }
}
