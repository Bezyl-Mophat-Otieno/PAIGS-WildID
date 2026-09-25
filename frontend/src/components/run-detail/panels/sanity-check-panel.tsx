import { SlotGrid } from "@/components/run-detail/slot-grid"
import { StatRow } from "@/components/run-detail/stat-row"
import { VerdictBadge } from "@/components/status-badge"
import { describeSingleReadReason } from "@/lib/single-read-reason"
import type { SanityCheckMetadata, SanityCheckOutput } from "@/types/api"

export function SanityCheckPanel({
  output,
  metadata,
}: {
  readonly output: SanityCheckOutput
  readonly metadata: SanityCheckMetadata | null
}) {
  return (
    <div className="flex flex-col gap-4">
      {metadata?.single_read_reason && (
        <p className="text-muted-foreground text-sm">
          {describeSingleReadReason(metadata.single_read_reason)}
        </p>
      )}
      <SlotGrid
        data={output}
        renderSlot={(result) => (
          <div>
            <StatRow label="N proportion" value={`${(result.n_proportion * 100).toFixed(2)}%`} />
            <StatRow label="Raw length" value={`${result.raw_length} bp`} />
            <StatRow label="Result" value={<VerdictBadge verdict={result.status} />} />
            {result.reason && <p className="text-status-critical mt-2 text-sm">{result.reason}</p>}
          </div>
        )}
      />
      {metadata?.thresholds && (
        <p className="text-muted-foreground text-xs">
          Max N-proportion tolerated: {metadata.thresholds.max_n_proportion} -- Min raw length:{" "}
          {metadata.thresholds.min_raw_length} bp
        </p>
      )}
    </div>
  )
}
