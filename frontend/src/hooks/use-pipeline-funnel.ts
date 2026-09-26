import { useQueries } from "@tanstack/react-query"
import { getStage } from "@/api/runs"
import { stageQueryKey } from "@/hooks/use-stage"
import { buildPipelineFunnel } from "@/lib/pipeline-funnel"
import { stageHasRun } from "@/lib/stages"
import type {
  Ab1ExtractionOutput,
  ConsensusOutput,
  StageSummary,
  TrimOutput,
  UsabilityCheckOutput,
} from "@/types/api"

const FUNNEL_STAGES = ["ab1_extraction", "trim", "consensus", "usability_check"] as const

// Shared by Run Detail's "Pipeline funnel" panel -- reads the same four
// stages' own records rather than recomputing any length, mirroring
// useEffectiveThresholds' fetch-once-per-panel pattern.
export function usePipelineFunnel(runId: string, stages: StageSummary[]) {
  const [ab1Query, trimQuery, consensusQuery, usabilityQuery] = useQueries({
    queries: FUNNEL_STAGES.map((stageType) => ({
      queryKey: stageQueryKey(runId, stageType),
      queryFn: () => getStage(runId, stageType),
      enabled: stageHasRun(stages, stageType),
    })),
  })

  const points = buildPipelineFunnel({
    ab1ExtractionOutput: ab1Query.data?.output as Ab1ExtractionOutput | undefined,
    trimOutput: trimQuery.data?.output as TrimOutput | undefined,
    consensusOutput:
      consensusQuery.data?.status === "completed"
        ? (consensusQuery.data.output as ConsensusOutput)
        : undefined,
    usabilityOutput: usabilityQuery.data?.output as UsabilityCheckOutput | undefined,
  })

  return {
    points,
    isLoading: [ab1Query, trimQuery, consensusQuery, usabilityQuery].some((q) => q.isLoading),
  }
}
