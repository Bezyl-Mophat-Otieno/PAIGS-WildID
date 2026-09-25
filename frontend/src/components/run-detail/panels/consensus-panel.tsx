import { ErrorPanel, SkippedPanel } from "@/components/run-detail/panel-states"
import { SequenceBlock } from "@/components/run-detail/sequence-block"
import { StatRow } from "@/components/run-detail/stat-row"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { ConsensusOutput, ErrorOutput } from "@/types/api"

const METHOD_LABELS: Record<string, string> = {
  agreement: "Reads agreed",
  ambiguity_consistency: "Ambiguity code resolved",
  quality_tiebreak: "Quality tiebreak",
}

export function ConsensusPanel({
  output,
  orientationFoundNoOverlap,
  singleReadReason,
}: {
  readonly output: ConsensusOutput | ErrorOutput | null
  readonly orientationFoundNoOverlap: boolean
  readonly singleReadReason?: string
}) {
  if (!output) {
    return (
      <SkippedPanel
        reason={
          orientationFoundNoOverlap
            ? "Orientation detection found no usable overlap between the two reads, so the run stopped before a consensus could be built."
            : (singleReadReason ??
              "Only one read survived cleanup -- consensus building only applies when two reads are being merged.")
        }
      />
    )
  }

  if ("error" in output) return <ErrorPanel message={output.error} />

  const notable = output.resolved_positions.filter((p) => p.method !== "agreement")

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-md">
        <StatRow label="Consensus length" value={`${output.consensus_length} bp`} />
        <StatRow label="Unresolved ambiguous positions" value={output.ambiguous_positions.length} />
      </div>
      <SequenceBlock sequence={output.consensus_sequence} copyLabel="consensus sequence" />
      {notable.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">Positions resolved beyond simple agreement</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Position</TableHead>
                <TableHead>Forward</TableHead>
                <TableHead>Reverse</TableHead>
                <TableHead>Resolved</TableHead>
                <TableHead>Method</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {notable.map((position) => (
                <TableRow key={position.position}>
                  <TableCell>{position.position}</TableCell>
                  <TableCell>
                    {position.forward_base} ({position.forward_quality})
                  </TableCell>
                  <TableCell>
                    {position.reverse_base} ({position.reverse_quality})
                  </TableCell>
                  <TableCell className="font-medium">{position.resolved_base}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {METHOD_LABELS[position.method] ?? position.method}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
