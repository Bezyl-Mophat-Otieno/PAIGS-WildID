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
    // Execute is synchronous today, so "in_progress" only really happens
    // for a run that was created but never executed -- polling covers that
    // edge case without needing a websocket/long-poll for the common one.
    refetchInterval: (query) => (query.state.data?.status === "in_progress" ? 2000 : false),
  })
}
