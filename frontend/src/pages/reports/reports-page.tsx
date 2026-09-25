import { useMemo } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { PackageOpen } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { downloadReportsExportBlob, listRuns } from "@/api/runs"
import { DataTable } from "@/components/data-table/data-table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"
import { useUserLookup } from "@/hooks/use-user-lookup"
import { triggerBlobDownload } from "@/lib/download"
import { getErrorMessage } from "@/lib/errors"
import { buildReportColumns } from "@/pages/reports/report-columns"

export function ReportsPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"

  const { data: runs, isLoading } = useQuery({ queryKey: ["runs"], queryFn: listRuns })
  const { byId } = useUserLookup()

  const columns = useMemo(
    () => buildReportColumns({ isAdmin, ownerById: byId }),
    [isAdmin, byId]
  )

  const exportAllMutation = useMutation({
    mutationFn: () => downloadReportsExportBlob(),
    onSuccess: (blob) => triggerBlobDownload(blob, "paigs_reports.zip"),
    onError: (error) =>
      toast.error(getErrorMessage(error, "Couldn't export reports.")),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-muted-foreground text-sm">
            {isAdmin ? "Every analyst's run reports." : "Your run reports."}
          </p>
        </div>
        <Button onClick={() => exportAllMutation.mutate()} disabled={exportAllMutation.isPending}>
          <PackageOpen className="size-4" />
          {exportAllMutation.isPending ? "Preparing ZIP..." : "Export all as ZIP"}
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <DataTable
          columns={columns}
          data={runs ?? []}
          searchPlaceholder="Search by sample ID..."
          onRowClick={(run) => navigate(`/runs/${run.id}`)}
          emptyState={<p className="text-muted-foreground text-sm">No runs yet.</p>}
        />
      )}
    </div>
  )
}
