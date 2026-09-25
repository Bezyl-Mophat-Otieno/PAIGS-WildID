import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Database } from "lucide-react"
import { listReferenceDatabaseVersions } from "@/api/reference-database"
import { DataTable } from "@/components/data-table/data-table"
import { StatRow } from "@/components/stat-row"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"
import { PublishVersionDialog } from "@/pages/reference-database/publish-version-dialog"
import { versionColumns } from "@/pages/reference-database/version-columns"

export function ReferenceDatabasePage() {
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"

  const { data: versions, isLoading } = useQuery({
    queryKey: ["reference-database", "versions"],
    queryFn: listReferenceDatabaseVersions,
  })

  const active = versions?.find((v) => v.is_active)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Reference Database</h1>
          <p className="text-muted-foreground text-sm">
            The curated species reference set every BLAST search runs against.
          </p>
        </div>
        {isAdmin && <PublishVersionDialog />}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="text-status-good size-4" />
            Active version
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : active ? (
            <div className="max-w-md">
              <StatRow label="Version" value={active.version} />
              <StatRow label="Sequences" value={active.sequence_count} />
              <StatRow label="Published" value={new Date(active.published_at).toLocaleString()} />
            </div>
          ) : (
            <div className="text-muted-foreground flex flex-col items-center gap-2 py-8 text-center text-sm">
              <Database className="size-6" />
              No reference database has been published yet.
              {!isAdmin && <p>An admin needs to publish one before any run can reach BLAST.</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Published versions</h2>
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <DataTable
            columns={versionColumns}
            data={versions ?? []}
            searchPlaceholder="Search by version..."
            emptyState={<p className="text-muted-foreground text-sm">No versions published yet.</p>}
          />
        )}
      </div>
    </div>
  )
}
