import { Upload } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function NewAnalysisPage() {
  return (
    <PagePlaceholder
      title="New Analysis"
      description="Dual-slot upload + threshold overrides, POST /runs then POST /runs/{id}/execute."
      icon={Upload}
    />
  )
}
