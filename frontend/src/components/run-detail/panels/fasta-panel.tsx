import { ErrorPanel } from "@/components/run-detail/panel-states"
import { SequenceBlock } from "@/components/run-detail/sequence-block"
import { StatRow } from "@/components/stat-row"
import type { ErrorOutput, FastaOutput } from "@/types/api"

export function FastaPanel({ output }: { readonly output: FastaOutput | ErrorOutput }) {
  if ("error" in output) return <ErrorPanel message={output.error} />

  return (
    <div className="flex max-w-2xl flex-col gap-3">
      <StatRow label="Sequence ID" value={output.sequence_id} />
      <StatRow label="Length" value={`${output.sequence_length} bp`} />
      <SequenceBlock sequence={output.fasta_content} copyLabel="FASTA content" />
    </div>
  )
}
