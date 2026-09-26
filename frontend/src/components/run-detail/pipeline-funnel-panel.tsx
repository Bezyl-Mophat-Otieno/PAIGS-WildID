import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "cn"
import { PipelineFunnelChart } from "@/components/charts/pipeline-funnel-chart"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import { usePipelineFunnel } from "@/hooks/use-pipeline-funnel"
import type { StageSummary } from "@/types/api"

export function PipelineFunnelPanel({
  runId,
  stages,
}: {
  readonly runId: string
  readonly stages: StageSummary[]
}) {
  const [open, setOpen] = useState(false)
  const { points, isLoading } = usePipelineFunnel(runId, stages)

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="border-border rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium">
        Pipeline funnel
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-border border-t px-4 py-3">
        {isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : points.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No cleanup stage has completed yet for this run.
          </p>
        ) : (
          <PipelineFunnelChart points={points} />
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
