import type { ReactNode } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "cn"

// Stat-tile figure contract (dataviz skill): label (sentence case, no
// trailing colon) + value (proportional figures, never tabular-nums --
// that's reserved for columns that must align vertically).
export function StatTile({
  label,
  value,
  icon,
  className,
}: {
  readonly label: string
  readonly value: ReactNode
  readonly icon?: ReactNode
  readonly className?: string
}) {
  return (
    <Card className={className}>
      <CardContent className="flex items-start justify-between gap-3">
        <div>
          <p className="text-muted-foreground text-sm">{label}</p>
          <p className={cn("mt-1 text-3xl font-semibold")}>{value}</p>
        </div>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </CardContent>
    </Card>
  )
}
