import { useQuery } from "@tanstack/react-query"
import { getStage } from "@/api/runs"
import type { StageType } from "@/types/api"

export function stageQueryKey(runId: string, stageType: StageType) {
  return ["runs", runId, "stages", stageType] as const
}

// Only fetch a stage's full detail once it has actually run -- a "pending"
// stage has no row on the backend yet (a fetch there would just 404).
export function useStage(runId: string, stageType: StageType, hasRun: boolean) {
  return useQuery({
    queryKey: stageQueryKey(runId, stageType),
    queryFn: () => getStage(runId, stageType),
    enabled: hasRun,
  })
}
