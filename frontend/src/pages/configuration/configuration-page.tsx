import { Settings } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function ConfigurationPage() {
  return (
    <PagePlaceholder
      title="Configuration"
      description="GET /config for everyone, PUT /config/{id} admin-only -- all 13 thresholds."
      icon={Settings}
    />
  )
}
