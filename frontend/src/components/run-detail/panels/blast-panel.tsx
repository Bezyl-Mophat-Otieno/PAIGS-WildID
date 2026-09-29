import { BlastHitChart } from "@/components/charts/blast-hit-chart"
import { ErrorPanel } from "@/components/run-detail/panel-states"
import { StatRow } from "@/components/stat-row"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { BlastOutput } from "@/types/api"

export function BlastPanel({
  output,
  ambiguousMarginPct,
}: {
  readonly output: BlastOutput
  // Stage 10's own margin threshold -- only known once Identification has
  // run, so this stays optional and the chart just skips the reference
  // line until then.
  readonly ambiguousMarginPct?: number
}) {
  if ("error" in output) return <ErrorPanel message={output.error} />

  // Undefined only for a run executed before search_mode existed -- those
  // always searched the local reference DB, so that's the safe fallback.
  const isRemote = output.search_mode === "remote"

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-md">
        <StatRow
          label="Search mode"
          value={
            <Badge variant={isRemote ? "default" : "secondary"}>
              {isRemote ? "Remote (NCBI)" : "Local"}
            </Badge>
          }
        />
        {isRemote ? (
          <>
            <StatRow label="NCBI database" value={output.remote_database ?? "—"} />
            {output.entrez_query && (
              <StatRow label="Entrez restriction" value={output.entrez_query} />
            )}
            <StatRow
              label="Queried"
              value={output.queried_at ? new Date(output.queried_at).toLocaleString() : "—"}
            />
          </>
        ) : (
          <StatRow label="Reference DB version" value={output.database_version} />
        )}
        <StatRow label="Query length" value={`${output.query_length} bp`} />
      </div>
      {isRemote && (
        <p className="text-muted-foreground max-w-md text-xs">
          NCBI's own database changes over time, so this exact search isn't guaranteed to
          reproduce identically later. This run's raw response is retained below as the audit
          record of exactly what NCBI returned.
        </p>
      )}
      {output.hits.length > 0 && (
        <BlastHitChart hits={output.hits} ambiguousMarginPct={ambiguousMarginPct} />
      )}
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
      {isRemote && output.raw_response && (
        <details className="text-sm">
          <summary className="text-muted-foreground cursor-pointer">
            Raw NCBI response (audit record)
          </summary>
          <pre className="border-border bg-muted mt-2 max-h-64 overflow-auto rounded-lg border p-3 text-xs">
            {output.raw_response}
          </pre>
        </details>
      )}
    </div>
  )
}
