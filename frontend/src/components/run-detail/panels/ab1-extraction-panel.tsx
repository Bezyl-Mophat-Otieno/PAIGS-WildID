import { ErrorPanel } from "@/components/run-detail/panel-states"
import { SequenceBlock } from "@/components/run-detail/sequence-block"
import { SlotGrid } from "@/components/run-detail/slot-grid"
import { StatRow } from "@/components/run-detail/stat-row"
import type { Ab1ExtractionOutput } from "@/types/api"

export function Ab1ExtractionPanel({ output }: { readonly output: Ab1ExtractionOutput }) {
  if ("error" in output) return <ErrorPanel message={output.error} />

  return (
    <SlotGrid
      data={output}
      renderSlot={(result) => (
        <div className="flex flex-col gap-3">
          <StatRow label="Raw length" value={`${result.raw_length} bp`} />
          <SequenceBlock sequence={result.raw_sequence} copyLabel="raw sequence" />
        </div>
      )}
    />
  )
}
