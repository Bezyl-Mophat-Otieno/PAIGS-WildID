import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { RunHeader } from "@/components/run-detail/run-header"
import { RunStepper } from "@/components/run-detail/run-stepper"
import { StagePanel } from "@/components/run-detail/stage-panel"
import { ThresholdsUsedPanel } from "@/components/run-detail/thresholds-used-panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"
import { useRun } from "@/hooks/use-run"
import { useStage } from "@/hooks/use-stage"
import { STAGE_LABELS } from "@/lib/stages"
import type { StageSummary, StageType } from "@/types/api"

function hasRunFn(summary: StageSummary | undefined) {
  return Boolean(summary && summary.status !== "pending")
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const { user } = useAuth()
  const { data: run, isLoading, isError } = useRun(runId)

  const [activeStage, setActiveStage] = useState<StageType | null>(null)

  // Default to wherever the run currently sits, but only once -- later
  // polling updates (a still-running run) shouldn't yank the analyst back
  // to current_stage while they're reading a different tab.
  useEffect(() => {
    if (run && activeStage === null) setActiveStage(run.current_stage)
  }, [run, activeStage])

  // Every hook below must run unconditionally on every render (rules of
  // hooks) -- fall back to safe/disabled values until `run` and
  // `activeStage` are actually known, and only branch into the loading/
  // error views after all hooks have been called.
  const stageMap = new Map((run?.stages ?? []).map((s) => [s.stage_type, s]))
  const effectiveActiveStage = activeStage ?? "import"
  const activeSummary = stageMap.get(effectiveActiveStage)

  const activeStageQuery = useStage(
    run?.id ?? "",
    effectiveActiveStage,
    Boolean(run) && hasRunFn(activeSummary)
  )
  const sanityCheckQuery = useStage(
    run?.id ?? "",
    "sanity_check",
    Boolean(run) && hasRunFn(stageMap.get("sanity_check"))
  )
  const orientationQuery = useStage(
    run?.id ?? "",
    "orientation",
    Boolean(run) && hasRunFn(stageMap.get("orientation"))
  )

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (isError || !run || !activeStage) {
    return <p className="text-status-critical text-sm">This run couldn't be found.</p>
  }

  const isOwner = user?.id === run.owner_id

  return (
    <div className="flex flex-col gap-6">
      <RunHeader run={run} isOwner={isOwner} />
      <ThresholdsUsedPanel runId={run.id} stages={run.stages} />
      <div className="flex gap-6">
        <RunStepper stages={run.stages} activeStage={activeStage} onSelect={setActiveStage} />
        <div className="border-border min-w-0 flex-1 rounded-lg border p-6">
          <h2 className="mb-4 text-lg font-semibold">{STAGE_LABELS[activeStage]}</h2>
          <StagePanel
            stageType={activeStage}
            stage={activeStageQuery.data}
            isLoading={activeStageQuery.isLoading}
            hasRun={hasRunFn(activeSummary)}
            runId={run.id}
            sampleId={run.sample_id}
            sanityCheckStage={sanityCheckQuery.data}
            orientationStage={orientationQuery.data}
          />
        </div>
      </div>
    </div>
  )
}
