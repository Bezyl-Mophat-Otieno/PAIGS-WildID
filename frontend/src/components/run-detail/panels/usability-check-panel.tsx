import { StatRow } from "@/components/stat-row"
import { VerdictBadge } from "@/components/status-badge"
import type { UsabilityCheckOutput } from "@/types/api"

export function UsabilityCheckPanel({ output }: { readonly output: UsabilityCheckOutput }) {
  return (
    <div className="max-w-md">
      <StatRow label="Final length" value={`${output.final_length} bp`} />
      <StatRow label="Mean quality" value={`Phred ${output.mean_quality.toFixed(1)}`} />
      <StatRow label="Unresolved ambiguous positions" value={output.ambiguous_positions} />
      <StatRow label="Result" value={<VerdictBadge verdict={output.status} />} />
      {output.reason && <p className="text-status-critical mt-2 text-sm">{output.reason}</p>}
    </div>
  )
}
