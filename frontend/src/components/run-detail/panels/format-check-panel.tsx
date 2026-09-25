import { CheckCircle2, XCircle } from "lucide-react"
import { SlotGrid } from "@/components/run-detail/slot-grid"
import { StatRow } from "@/components/stat-row"
import type { FormatCheckOutput } from "@/types/api"

export function FormatCheckPanel({ output }: { readonly output: FormatCheckOutput }) {
  return (
    <SlotGrid
      data={output}
      renderSlot={(result) => (
        <div>
          <StatRow label="Filename" value={result.filename} />
          <StatRow
            label="Valid AB1 structure"
            value={
              result.valid ? (
                <span className="text-status-good inline-flex items-center gap-1.5">
                  <CheckCircle2 className="size-4" /> Valid
                </span>
              ) : (
                <span className="text-status-critical inline-flex items-center gap-1.5">
                  <XCircle className="size-4" /> Invalid
                </span>
              )
            }
          />
          {result.reason && <p className="text-status-critical mt-2 text-sm">{result.reason}</p>}
        </div>
      )}
    />
  )
}
