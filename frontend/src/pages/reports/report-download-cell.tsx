import { useMutation } from "@tanstack/react-query"
import { Download } from "lucide-react"
import { toast } from "sonner"
import { downloadReportBlob } from "@/api/runs"
import { Button } from "@/components/ui/button"
import { triggerBlobDownload } from "@/lib/download"
import { getErrorMessage } from "@/lib/errors"

export function ReportDownloadCell({
  runId,
  sampleId,
  likelyAvailable,
}: {
  readonly runId: string
  readonly sampleId: string
  readonly likelyAvailable: boolean
}) {
  const mutation = useMutation({
    mutationFn: () => downloadReportBlob(runId),
    onSuccess: (blob) => triggerBlobDownload(blob, `${sampleId}_report.pdf`),
    onError: (error) => toast.error(getErrorMessage(error, "Couldn't download this report.")),
  })

  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={mutation.isPending}
      // Report is Stage 12, the pipeline's last step -- a run only reaches
      // status "completed" if every prior stage (including Report) already
      // succeeded, so this is a reliable enough hint without a per-row
      // fetch. The click itself still goes through the real endpoint
      // either way, so a wrong guess here just surfaces the server's own
      // "no completed report yet" message instead of silently failing.
      title={likelyAvailable ? undefined : "This run may not have a completed report"}
      onClick={(e) => {
        e.stopPropagation()
        mutation.mutate()
      }}
    >
      <Download className="size-4" />
      {mutation.isPending ? "Preparing..." : "Download"}
    </Button>
  )
}
