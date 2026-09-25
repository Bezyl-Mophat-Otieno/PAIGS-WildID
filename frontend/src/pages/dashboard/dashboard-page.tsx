import { LayoutDashboard } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function DashboardPage() {
  return (
    <PagePlaceholder
      title="Dashboard"
      description="KPI tiles, species breakdown, and quality histogram from GET /dashboard/stats."
      icon={LayoutDashboard}
    />
  )
}
