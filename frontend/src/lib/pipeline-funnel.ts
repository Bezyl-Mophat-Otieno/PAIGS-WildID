import type {
  Ab1ExtractionOutput,
  ConsensusOutput,
  ReadSlotKey,
  TrimOutput,
  UsabilityCheckOutput,
} from "@/types/api"

export interface FunnelPoint {
  stage: string
  forward?: number
  reverse?: number
  merged?: number
}

function slotValue<T>(
  output: Partial<Record<ReadSlotKey, T>> | undefined,
  slot: ReadSlotKey,
  pick: (result: T) => number
): number | undefined {
  const entry = output?.[slot]
  return entry ? pick(entry) : undefined
}

// Pure builder over already-fetched stage outputs (DESIGN.md's pipeline
// funnel: raw -> trimmed -> consensus -> final, showing where length was
// lost). Each row's keys come from that row's OWN stage output -- not a
// single hoisted "is this a two-read run" flag -- because the QC-fallback
// single-read path (CLAUDE.md Stage 3) can genuinely extract two raw reads
// and then trim only the one that survived.
export function buildPipelineFunnel({
  ab1ExtractionOutput,
  trimOutput,
  consensusOutput,
  usabilityOutput,
}: {
  readonly ab1ExtractionOutput: Ab1ExtractionOutput | undefined
  readonly trimOutput: TrimOutput | undefined
  readonly consensusOutput: ConsensusOutput | undefined
  readonly usabilityOutput: UsabilityCheckOutput | undefined
}): FunnelPoint[] {
  const points: FunnelPoint[] = []

  const rawBySlot =
    ab1ExtractionOutput && !("error" in ab1ExtractionOutput) ? ab1ExtractionOutput : undefined
  if (rawBySlot && Object.keys(rawBySlot).length > 0) {
    points.push({
      stage: "Raw",
      forward: slotValue(rawBySlot, "forward", (r) => r.raw_length),
      reverse: slotValue(rawBySlot, "reverse", (r) => r.raw_length),
    })
  }

  if (trimOutput && Object.keys(trimOutput).length > 0) {
    points.push({
      stage: "Trimmed",
      forward: slotValue(trimOutput, "forward", (r) => r.trimmed_length),
      reverse: slotValue(trimOutput, "reverse", (r) => r.trimmed_length),
    })
  }

  if (consensusOutput) {
    points.push({ stage: "Consensus", merged: consensusOutput.consensus_length })
  }

  if (usabilityOutput) {
    points.push({ stage: "Final", merged: usabilityOutput.final_length })
  }

  return points
}
