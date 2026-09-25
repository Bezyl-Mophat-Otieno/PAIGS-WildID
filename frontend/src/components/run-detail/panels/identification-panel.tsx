import { StatRow } from "@/components/stat-row"
import { VerdictBadge } from "@/components/status-badge"
import type { IdentificationOutput } from "@/types/api"

export function IdentificationPanel({ output }: { readonly output: IdentificationOutput }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-md">
        <StatRow label="Candidate species" value={output.candidate_species ?? "—"} />
        <StatRow
          label="Identity"
          value={output.identity !== null ? `${output.identity.toFixed(2)}%` : "—"}
        />
        <StatRow
          label="Coverage"
          value={output.coverage !== null ? `${output.coverage.toFixed(1)}%` : "—"}
        />
        <StatRow label="Result" value={<VerdictBadge verdict={output.status} />} />
      </div>
      {output.reason && <p className="text-muted-foreground max-w-md text-sm">{output.reason}</p>}
      <p className="text-muted-foreground text-xs">
        Thresholds applied: min identity {output.thresholds_applied.min_identity_pct}% -- min
        coverage {output.thresholds_applied.min_coverage_pct}% -- ambiguous margin{" "}
        {output.thresholds_applied.ambiguous_margin_pct} points
      </p>
    </div>
  )
}
