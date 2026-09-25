import { useMutation } from "@tanstack/react-query"
import { Download, FileText } from "lucide-react"
import { toast } from "sonner"
import { downloadReportBlob } from "@/api/runs"
import { Button } from "@/components/ui/button"
import { triggerBlobDownload } from "@/lib/download"
import { getErrorMessage } from "@/lib/errors"

export function ReportPanel({
  runId,
  sampleId,
}: {
  readonly runId: string
  readonly sampleId: string
}) {
  const mutation = useMutation({
    mutationFn: () => downloadReportBlob(runId),
    onSuccess: (blob) => triggerBlobDownload(blob, `${sampleId}_report.pdf`),
    onError: (error) => toast.error(getErrorMessage(error, "Couldn't download the report.")),
  })

  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <FileText className="text-muted-foreground size-8" />
      <p className="max-w-sm text-sm">
        Every prior stage's data, assembled into one auditable PDF -- sample ID, QC results,
        trimming, orientation, consensus, thresholds used, BLAST candidates, and final status.
      </p>
      <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
        <Download className="size-4" />
        {mutation.isPending ? "Preparing..." : "Download report PDF"}
      </Button>
    </div>
  )
}
