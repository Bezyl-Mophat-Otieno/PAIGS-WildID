import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { ThresholdDiffRow } from "@/lib/rerun-prefill"

function formatValue(value: number | undefined) {
  return value === undefined ? "—" : value
}

export function ThresholdDiffTable({ rows }: { readonly rows: ThresholdDiffRow[] }) {
  const changed = rows.filter((r) => r.changed)
  const unchanged = rows.filter((r) => !r.changed)

  return (
    <div className="flex flex-col gap-4">
      {changed.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No threshold differs between these two runs.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Threshold</TableHead>
              <TableHead className="text-right">Source</TableHead>
              <TableHead className="text-right">Rerun</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {changed.map((row) => (
              <TableRow key={row.key}>
                <TableCell>{row.label}</TableCell>
                <TableCell className="text-status-critical text-right tabular-nums">
                  {formatValue(row.sourceValue)}
                </TableCell>
                <TableCell className="text-status-good text-right font-medium tabular-nums">
                  {formatValue(row.rerunValue)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {unchanged.length > 0 && (
        <details className="text-sm">
          <summary className="text-muted-foreground cursor-pointer">
            {unchanged.length} unchanged threshold{unchanged.length === 1 ? "" : "s"}
          </summary>
          <Table className="mt-2">
            <TableBody>
              {unchanged.map((row) => (
                <TableRow key={row.key}>
                  <TableCell className="text-muted-foreground">{row.label}</TableCell>
                  <TableCell className="text-muted-foreground text-right tabular-nums">
                    {formatValue(row.sourceValue)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}
    </div>
  )
}
