import { Database } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function ReferenceDatabasePage() {
  return (
    <PagePlaceholder
      title="Reference Database"
      description="GET /reference-database/versions + /active for everyone, publish is admin-only."
      icon={Database}
    />
  )
}
