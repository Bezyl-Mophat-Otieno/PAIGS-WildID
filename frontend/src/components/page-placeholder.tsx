import type { LucideIcon } from "lucide-react"
import { Construction } from "lucide-react"

interface PagePlaceholderProps {
  readonly title: string
  readonly description?: string
  readonly icon?: LucideIcon
}

// Marks a route that's wired up (nav, routing, auth guard) but whose screen
// hasn't been built yet -- swapped out interface by interface.
export function PagePlaceholder({
  title,
  description,
  icon: Icon = Construction,
}: PagePlaceholderProps) {
  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {description && <p className="text-muted-foreground text-sm">{description}</p>}
      <div className="border-border mt-6 flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-24">
        <Icon className="text-muted-foreground size-8" />
        <p className="text-muted-foreground text-sm">
          This screen hasn't been built yet.
        </p>
      </div>
    </div>
  )
}
