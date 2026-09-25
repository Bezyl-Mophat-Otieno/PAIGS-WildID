import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "cn"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import { useEffectiveThresholds } from "@/hooks/use-effective-thresholds"
import { STAGE_LABELS } from "@/lib/stages"
import type { StageSummary } from "@/types/api"

export function ThresholdsUsedPanel({
  runId,
  stages,
}: {
  readonly runId: string
  readonly stages: StageSummary[]
}) {
  const [open, setOpen] = useState(false)
  const { rows, isLoading } = useEffectiveThresholds(runId, stages)

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="border-border rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium">
        Thresholds used
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-border border-t px-4 py-3">
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No threshold-gated stage has run yet for this run.
          </p>
        ) : (
          <dl className="grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2">
            {rows.map((row) => (
              <div key={row.key} className="border-border/60 flex items-center justify-between border-b py-1.5 text-sm">
                <dt className="text-muted-foreground">
                  {STAGE_LABELS[row.stageType]} {"–"} {row.paramName}
                </dt>
                <dd className="font-medium">{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
