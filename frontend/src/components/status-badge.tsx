import {
  CheckCircle2,
  Circle,
  CircleDashed,
  Info,
  Loader2,
  PauseCircle,
  XCircle,
} from "lucide-react"
import { cn } from "cn"
import type { RunStatus, StageStatus } from "@/types/api"

// Two distinct axes (DESIGN.md "Stage status & badge system"): Stage.status
// is *execution* state (did the step run), rendered on the stepper icon.
// Biological verdict (PASS/FAIL/AMBIGUOUS/REVIEW REQUIRED) is a completed
// stage's own finding, rendered inside its panel -- never on the stepper
// icon, so "this step broke" and "this step found something worth
// reviewing" never look the same.

const STAGE_STATUS_CONFIG: Record<
  StageStatus,
  { label: string; icon: typeof Circle; className: string }
> = {
  pending: {
    label: "Pending",
    icon: Circle,
    className: "text-muted-foreground border-border",
  },
  running: {
    label: "Running",
    icon: Loader2,
    className: "text-primary border-primary/40",
  },
  completed: {
    label: "Completed",
    icon: CheckCircle2,
    className: "text-status-good border-status-good/40",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "text-status-critical border-status-critical/40",
  },
  skipped: {
    label: "Skipped",
    icon: CircleDashed,
    className: "text-muted-foreground border-border border-dashed",
  },
}

export function StageStatusBadge({ status }: { readonly status: StageStatus }) {
  const config = STAGE_STATUS_CONFIG[status]
  const Icon = config.icon

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        config.className
      )}
    >
      <Icon className={cn("size-3.5", status === "running" && "animate-spin")} />
      {config.label}
    </span>
  )
}

// A run's overall execution status -- distinct from any single stage's:
// "completed" here means the pipeline ran to its natural end (which may
// still be a biological FAIL/REVIEW REQUIRED), "failed" means a hard stop.
const RUN_STATUS_CONFIG: Record<
  RunStatus,
  { label: string; icon: typeof Circle; className: string }
> = {
  in_progress: {
    label: "In Progress",
    icon: Loader2,
    className: "text-primary border-primary/40",
  },
  paused: {
    label: "Paused",
    icon: PauseCircle,
    className: "text-muted-foreground border-border",
  },
  completed: {
    label: "Completed",
    icon: CheckCircle2,
    className: "text-status-good border-status-good/40",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "text-status-critical border-status-critical/40",
  },
}

export function RunStatusBadge({ status }: { readonly status: RunStatus }) {
  const config = RUN_STATUS_CONFIG[status]
  const Icon = config.icon

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm font-medium",
        config.className
      )}
    >
      <Icon className={cn("size-4", status === "in_progress" && "animate-spin")} />
      {config.label}
    </span>
  )
}

export type Verdict =
  | "PASS"
  | "FAIL"
  | "AMBIGUOUS"
  | "REVIEW REQUIRED"
  | "NO OVERLAP FOUND"

const VERDICT_CONFIG: Record<
  Verdict,
  { icon: typeof Circle; className: string }
> = {
  PASS: { icon: CheckCircle2, className: "text-status-good border-status-good/40" },
  FAIL: { icon: XCircle, className: "text-status-critical border-status-critical/40" },
  AMBIGUOUS: { icon: Info, className: "text-status-warning border-status-warning/40" },
  "REVIEW REQUIRED": {
    icon: Info,
    className: "text-status-serious border-status-serious/40",
  },
  "NO OVERLAP FOUND": {
    icon: Info,
    className: "text-muted-foreground border-border",
  },
}

export function VerdictBadge({ verdict }: { readonly verdict: Verdict }) {
  const config = VERDICT_CONFIG[verdict]
  const Icon = config.icon

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold",
        config.className
      )}
    >
      <Icon className="size-3.5" />
      {verdict}
    </span>
  )
}
