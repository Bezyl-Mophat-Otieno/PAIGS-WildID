import type { ReactNode } from "react"
import { Link } from "react-router-dom"
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
  href,
}: {
  readonly label: string
  readonly value: ReactNode
  readonly icon?: ReactNode
  readonly className?: string
  // When set, the tile becomes a link to wherever the underlying figure's
  // detail lives -- e.g. "Pending review" drilling into the filtered run
  // list, rather than leaving an analyst with a number and no next step.
  readonly href?: string
}) {
  const card = (
    <Card className={cn(href && "hover:border-primary/40 transition-colors", className)}>
      <CardContent className="flex items-start justify-between gap-3">
        <div>
          <p className="text-muted-foreground text-sm">{label}</p>
          <p className={cn("mt-1 text-3xl font-semibold")}>{value}</p>
        </div>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </CardContent>
    </Card>
  )

  return href ? <Link to={href}>{card}</Link> : card
}
