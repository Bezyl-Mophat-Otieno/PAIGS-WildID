import { Info } from "lucide-react"
import { SkippedPanel } from "@/components/run-detail/panel-states"
import { StatRow } from "@/components/stat-row"
import { VerdictBadge } from "@/components/status-badge"
import type { OrientationOutput } from "@/types/api"

const ORIENTATION_LABELS: Record<OrientationOutput["orientation"], string> = {
  as_is: "As uploaded (no reverse-complement needed)",
  reverse_read_reverse_complemented: "Reverse read was reverse-complemented",
  no_overlap_found: "No usable overlap found",
}

export function OrientationPanel({
  output,
  singleReadReason,
}: {
  readonly output: OrientationOutput | null
  readonly singleReadReason?: string
}) {
  if (!output) {
    return (
      <SkippedPanel
        reason={
          singleReadReason ??
          "Only one read survived cleanup -- orientation detection only applies when two reads are being compared."
        }
      />
    )
  }

  if (output.orientation === "no_overlap_found") {
    return (
      <div className="flex flex-col gap-4">
        <VerdictBadge verdict="NO OVERLAP FOUND" />
        <p className="text-muted-foreground max-w-md text-sm">
          Neither orientation attempt produced a usable overlap between the two reads -- this most
          often means the two files aren't actually a matching forward/reverse pair. The run stops
          here rather than guessing.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-md">
      <StatRow label="Detected orientation" value={ORIENTATION_LABELS[output.orientation]} />
      <StatRow label="Alignment score" value={output.alignment_score} />
      <StatRow label="Overlap length" value={`${output.overlap_length} bp`} />
      <StatRow
        label="Overlap identity"
        value={output.identity !== null ? `${(output.identity * 100).toFixed(1)}%` : "—"}
      />
      {output.label_orientation_mismatch && (
        <div className="text-muted-foreground mt-3 flex items-start gap-2 text-sm">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p>
            The Forward/Reverse upload labels didn't match what was actually detected -- noted for
            the record, but this never blocks the run.
          </p>
        </div>
      )}
    </div>
  )
}
