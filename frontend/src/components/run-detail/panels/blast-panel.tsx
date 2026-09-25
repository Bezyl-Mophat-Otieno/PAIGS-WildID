import { ErrorPanel } from "@/components/run-detail/panel-states"
import { StatRow } from "@/components/stat-row"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { BlastOutput } from "@/types/api"

export function BlastPanel({ output }: { readonly output: BlastOutput }) {
  if ("error" in output) return <ErrorPanel message={output.error} />

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-md">
        <StatRow label="Reference DB version" value={output.database_version} />
        <StatRow label="Query length" value={`${output.query_length} bp`} />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Species</TableHead>
            <TableHead className="text-right">Identity</TableHead>
            <TableHead className="text-right">Coverage</TableHead>
            <TableHead className="text-right">E-value</TableHead>
            <TableHead className="text-right">Bit score</TableHead>
            <TableHead>Accession</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {output.hits.map((hit) => (
            <TableRow key={hit.rank}>
              <TableCell>{hit.rank}</TableCell>
              <TableCell className="italic">{hit.species}</TableCell>
              <TableCell className="text-right tabular-nums">{hit.identity.toFixed(2)}%</TableCell>
              <TableCell className="text-right tabular-nums">{hit.coverage.toFixed(1)}%</TableCell>
              <TableCell className="text-right tabular-nums">{hit.evalue}</TableCell>
              <TableCell className="text-right tabular-nums">{hit.bit_score}</TableCell>
              <TableCell className="text-muted-foreground">{hit.accession}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
