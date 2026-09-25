import { Users } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function TeamPage() {
  return (
    <PagePlaceholder
      title="Team / Users"
      description="POST /admin/invite, GET /admin/users -- admin only."
      icon={Users}
    />
  )
}
