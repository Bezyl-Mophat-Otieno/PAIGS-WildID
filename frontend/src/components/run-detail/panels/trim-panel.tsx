import { SequenceBlock } from "@/components/run-detail/sequence-block"
import { SlotGrid } from "@/components/run-detail/slot-grid"
import { StatRow } from "@/components/run-detail/stat-row"
import type { TrimOutput } from "@/types/api"

export function TrimPanel({ output }: { readonly output: TrimOutput }) {
  return (
    <SlotGrid
      data={output}
      renderSlot={(result) => (
        <div className="flex flex-col gap-3">
          <StatRow label="Trimmed length" value={`${result.trimmed_length} bp`} />
          <StatRow label="Kept window" value={`${result.trim_start}–${result.trim_end}`} />
          <StatRow
            label="Quality threshold"
            value={`Phred ≥ ${result.trim_params.quality_threshold}`}
          />
          <SequenceBlock sequence={result.trimmed_sequence} copyLabel="trimmed sequence" />
        </div>
      )}
    />
  )
}
