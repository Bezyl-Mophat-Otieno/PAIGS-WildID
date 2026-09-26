import type { ReactNode } from "react"
import { cn } from "cn"
import { READ_SLOT_LABELS } from "@/lib/stages"
import type { ReadSlotKey } from "@/types/api"

export function SlotGrid<T>({
  data,
  renderSlot,
}: {
  readonly data: Partial<Record<ReadSlotKey, T>>
  readonly renderSlot: (data: T, slot: ReadSlotKey) => ReactNode
}) {
  const slots = (Object.keys(READ_SLOT_LABELS) as ReadSlotKey[]).filter((slot) => data[slot])

  return (
    <div className={cn("grid gap-4", slots.length === 2 && "sm:grid-cols-2")}>
      {slots.map((slot) => (
        <div key={slot} className="border-border rounded-lg border p-4">
          <p className="mb-3 text-sm font-semibold">{READ_SLOT_LABELS[slot]}</p>
          {renderSlot(data[slot]!, slot)}
        </div>
      ))}
    </div>
  )
}
