import { useQuery } from "@tanstack/react-query"
import { getRun } from "@/api/runs"

export function runQueryKey(runId: string) {
  return ["runs", runId] as const
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: runQueryKey(runId ?? ""),
    queryFn: () => getRun(runId!),
    enabled: Boolean(runId),
    // Stages 1-8 are synchronous, so "in_progress" mostly meant "created
    // but never executed" -- until blast.mode="remote" (the default): a
    // real NCBI search can legitimately run for minutes in the
    // background (see CLAUDE.md's Stage 9 section), during which the Run
    // sits at "in_progress"/current_stage="blast" for real, not just
    // momentarily. This poll is what actually surfaces its eventual
    // completed/failed transition -- no websocket/long-poll needed.
    refetchInterval: (query) => (query.state.data?.status === "in_progress" ? 2000 : false),
  })
}
