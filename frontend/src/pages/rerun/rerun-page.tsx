import { useParams } from "react-router-dom"
import { GitCompareArrows } from "lucide-react"
import { PagePlaceholder } from "@/components/page-placeholder"

export function RerunPage() {
  const { runId } = useParams<{ runId: string }>()

  return (
    <PagePlaceholder
      title={`Rerun ${runId}`}
      description="POST /runs/{id}/rerun, then a side-by-side threshold + result comparison."
      icon={GitCompareArrows}
    />
  )
}
