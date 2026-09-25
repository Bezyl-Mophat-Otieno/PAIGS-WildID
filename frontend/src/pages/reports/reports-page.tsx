import { FileText } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function ReportsPage() {
  return (
    <PagePlaceholder
      title="Reports"
      description="Per-run GET /runs/{id}/report, bulk GET /runs/reports/export as a ZIP."
      icon={FileText}
    />
  )
}
