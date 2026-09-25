import {
  CheckCircle2,
  Circle,
  CircleDashed,
  Loader2,
  XCircle,
} from "lucide-react"
import { cn } from "cn"
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/stages"
import type { StageStatus, StageSummary, StageType } from "@/types/api"

const ICON: Record<StageStatus, typeof Circle> = {
  pending: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  skipped: CircleDashed,
}

const ICON_CLASS: Record<StageStatus, string> = {
  pending: "text-muted-foreground",
  running: "text-primary animate-spin",
  completed: "text-status-good",
  failed: "text-status-critical",
  skipped: "text-muted-foreground",
}

export function RunStepper({
  stages,
  activeStage,
  onSelect,
}: {
  readonly stages: StageSummary[]
  readonly activeStage: StageType
  readonly onSelect: (stage: StageType) => void
}) {
  const stageMap = new Map(stages.map((s) => [s.stage_type, s]))

  return (
    <nav className="flex w-56 shrink-0 flex-col gap-0.5">
      {STAGE_ORDER.map((stageType) => {
        const status = stageMap.get(stageType)?.status ?? "pending"
        const Icon = ICON[status]
        const isActive = stageType === activeStage
        const isClickable = status !== "pending"

        return (
          <button
            key={stageType}
            type="button"
            disabled={!isClickable}
            onClick={() => onSelect(stageType)}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors",
              isClickable ? "hover:bg-muted cursor-pointer" : "cursor-not-allowed opacity-50",
              isActive && "bg-accent text-accent-foreground font-medium"
            )}
          >
            <Icon className={cn("size-4 shrink-0", ICON_CLASS[status])} />
            {STAGE_LABELS[stageType]}
          </button>
        )
      })}
    </nav>
  )
}
