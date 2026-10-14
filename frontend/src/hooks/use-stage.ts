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
    // A stage itself can sit at "running" for a real, possibly multi-
    // minute duration -- blast.mode="remote" is the one case today (see
    // CLAUDE.md's Stage 9 section) -- not just the Run as a whole, which
    // is what useRun's own refetchInterval already watches. Without this,
    // `hasRun` flips enabled:true the moment the stage starts running,
    // this fetches once, caches a {status: "running", output: null}
    // snapshot, and then never refetches again -- the panel is stuck
    // showing "running" even long after the backend actually finishes,
    // until something else (a manual page refresh) forces a re-fetch.
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  })
}
