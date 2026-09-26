import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { listRuns } from "@/api/runs"
import { DataTable } from "@/components/data-table/data-table"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"
import { useUserLookup } from "@/hooks/use-user-lookup"
import { buildRunColumns } from "@/pages/run-history/run-columns"
import type { IdentificationStatus } from "@/types/api"

// URL-friendly outcome values (matches this app's existing snake_case
// convention for status query params) mapped to the identification
// stage's own verdict strings -- kept separate so the URL never has to
// carry a literal space (as in "REVIEW REQUIRED").
const OUTCOME_PARAM_TO_STATUS: Record<string, IdentificationStatus> = {
  review_required: "REVIEW REQUIRED",
  ambiguous: "AMBIGUOUS",
  pass: "PASS",
}

export function RunHistoryPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: runs, isLoading } = useQuery({ queryKey: ["runs"], queryFn: listRuns })
  const { byId } = useUserLookup()

  const isAdmin = user?.role === "admin"
  const columns = useMemo(
    () => buildRunColumns({ isAdmin, ownerById: byId }),
    [isAdmin, byId]
  )

  const outcomeParam = searchParams.get("outcome") ?? "all"
  const filteredRuns = useMemo(() => {
    if (outcomeParam === "all") return runs ?? []
    const targetStatus = OUTCOME_PARAM_TO_STATUS[outcomeParam]
    return (runs ?? []).filter((run) => run.identification_status === targetStatus)
  }, [runs, outcomeParam])

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

      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-sm">Outcome</span>
        <Select
          value={outcomeParam}
          onValueChange={(value) =>
            setSearchParams(value === "all" ? {} : { outcome: value })
          }
        >
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All runs</SelectItem>
            <SelectItem value="review_required">Needs review</SelectItem>
            <SelectItem value="ambiguous">Ambiguous</SelectItem>
            <SelectItem value="pass">Passed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <DataTable
          columns={columns}
          data={filteredRuns}
          searchPlaceholder="Search by sample ID..."
          onRowClick={(run) => navigate(`/runs/${run.id}`)}
          emptyState={
            <div className="flex flex-col items-center gap-2 py-8">
              <p className="text-muted-foreground text-sm">
                {outcomeParam === "all" ? "No runs yet." : "No runs match this outcome."}
              </p>
              {outcomeParam === "all" && (
                <Button asChild variant="outline" size="sm">
                  <Link to="/new-analysis">Start your first analysis</Link>
                </Button>
              )}
            </div>
          }
        />
      )}
    </div>
  )
}
