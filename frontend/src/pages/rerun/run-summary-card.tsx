import { Link } from "react-router-dom"
import { RunStatusBadge, VerdictBadge } from "@/components/status-badge"
import { StatRow } from "@/components/stat-row"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { IdentificationOutput, Run } from "@/types/api"

export function RunSummaryCard({
  title,
  run,
  identification,
}: {
  readonly title: string
  readonly run: Run
  readonly identification: IdentificationOutput | undefined
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          {title}
          <RunStatusBadge status={run.status} />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Link to={`/runs/${run.id}`} className="text-primary text-sm hover:underline">
          {run.sample_id}
        </Link>
        <div className="mt-2">
          <StatRow label="Current stage" value={run.current_stage} />
          {identification ? (
            <>
              <StatRow label="Candidate species" value={identification.candidate_species ?? "—"} />
              <StatRow
                label="Identity"
                value={
                  identification.identity !== null ? `${identification.identity.toFixed(2)}%` : "—"
                }
              />
              <StatRow
                label="Coverage"
                value={
                  identification.coverage !== null ? `${identification.coverage.toFixed(1)}%` : "—"
                }
              />
              <StatRow label="Result" value={<VerdictBadge verdict={identification.status} />} />
            </>
          ) : (
            <StatRow label="Identification" value="Not reached" />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
