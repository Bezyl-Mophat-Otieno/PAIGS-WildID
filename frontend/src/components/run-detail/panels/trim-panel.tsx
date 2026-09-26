import { ChromatogramDialog } from "@/components/charts/chromatogram/chromatogram-dialog"
import { TrimQualityChart } from "@/components/charts/trim-quality-chart"
import { SequenceBlock } from "@/components/run-detail/sequence-block"
import { SlotGrid } from "@/components/run-detail/slot-grid"
import { StatRow } from "@/components/stat-row"
import type { Ab1ExtractionOutput, ReadSlotKey, TrimOutput } from "@/types/api"

export function TrimPanel({
  runId,
  output,
  ab1ExtractionOutput,
}: {
  readonly runId: string
  readonly output: TrimOutput
  readonly ab1ExtractionOutput: Ab1ExtractionOutput | undefined
}) {
  const rawBySlot =
    ab1ExtractionOutput && !("error" in ab1ExtractionOutput) ? ab1ExtractionOutput : undefined

  return (
    <SlotGrid
      data={output}
      renderSlot={(result, slot) => {
        const raw = rawBySlot?.[slot as ReadSlotKey]
        return (
          <div className="flex flex-col gap-4">
            {/* Heavy-on-visuals mandate: the chart leads, raw numbers follow --
                not the other way around. */}
            {raw && (
              <TrimQualityChart
                qualityScores={raw.quality_scores}
                trimStart={result.trim_start}
                trimEnd={result.trim_end}
                qualityThreshold={result.trim_params.quality_threshold}
              />
            )}
            <div>
              <StatRow label="Trimmed length" value={`${result.trimmed_length} bp`} />
              <StatRow label="Kept window" value={`${result.trim_start}–${result.trim_end}`} />
              <StatRow
                label="Quality threshold"
                value={`Phred ≥ ${result.trim_params.quality_threshold}`}
              />
            </div>
            <SequenceBlock sequence={result.trimmed_sequence} copyLabel="trimmed sequence" />
            <div className="self-start">
              <ChromatogramDialog
                runId={runId}
                slot={slot}
                trimRange={{ start: result.trim_start, end: result.trim_end }}
                initialPosition={result.trim_start}
              />
            </div>
          </div>
        )
      }}
    />
  )
}
