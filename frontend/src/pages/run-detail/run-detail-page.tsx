import { useParams } from "react-router-dom"
import { FlaskConical } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()

  return (
    <PagePlaceholder
      title={`Run ${runId}`}
      description="Tab-based stage inspector -- GET /runs/{id} drives the stepper, GET /runs/{id}/stages/{type} per tab."
      icon={FlaskConical}
    />
  )
}
