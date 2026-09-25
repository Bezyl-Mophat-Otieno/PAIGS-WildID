import { StatRow } from "@/components/run-detail/stat-row"
import { READ_SLOT_LABELS } from "@/lib/stages"
import type { ImportOutput } from "@/types/api"

export function ImportPanel({ output }: { readonly output: ImportOutput }) {
  return (
    <div className="max-w-md">
      {output.slots.map((slot, index) => (
        <StatRow
          key={slot}
          label={READ_SLOT_LABELS[slot]}
          value={output.original_filenames[index]}
        />
      ))}
    </div>
  )
}
