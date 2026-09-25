import type { ReactNode } from "react"

export function StatRow({ label, value }: { readonly label: string; readonly value: ReactNode }) {
  return (
    <div className="border-border/60 flex items-center justify-between border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
