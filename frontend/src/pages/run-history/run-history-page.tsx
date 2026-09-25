import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { Link, useNavigate } from "react-router-dom"
import { listRuns } from "@/api/runs"
import { DataTable } from "@/components/data-table/data-table"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"
import { useUserLookup } from "@/hooks/use-user-lookup"
import { buildRunColumns } from "@/pages/run-history/run-columns"

export function RunHistoryPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { data: runs, isLoading } = useQuery({ queryKey: ["runs"], queryFn: listRuns })
  const { byId } = useUserLookup()

  const isAdmin = user?.role === "admin"
  const columns = useMemo(
    () => buildRunColumns({ isAdmin, ownerById: byId }),
    [isAdmin, byId]
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Run History</h1>
          <p className="text-muted-foreground text-sm">
            {isAdmin ? "Every analyst's runs." : "Your runs."}
          </p>
        </div>
        <Button asChild>
          <Link to="/new-analysis">
            <Upload className="size-4" />
            New Analysis
          </Link>
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
          emptyState={
            <div className="flex flex-col items-center gap-2 py-8">
              <p className="text-muted-foreground text-sm">No runs yet.</p>
              <Button asChild variant="outline" size="sm">
                <Link to="/new-analysis">Start your first analysis</Link>
              </Button>
            </div>
          }
        />
      )}
    </div>
  )
}
