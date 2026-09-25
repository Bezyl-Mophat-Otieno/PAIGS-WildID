import { History } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function RunHistoryPage() {
  return (
    <PagePlaceholder
      title="Run History"
      description="GET /runs, filterable/sortable via TanStack Table."
      icon={History}
    />
  )
}
