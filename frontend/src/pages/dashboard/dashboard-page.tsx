import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, FlaskConical, ShieldCheck } from "lucide-react"
import { fetchDashboardStats } from "@/api/dashboard"
import { QualityHistogram } from "@/components/charts/quality-histogram"
import { SpeciesDonut } from "@/components/charts/species-donut"
import { StatTile } from "@/components/stat-tile"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/context/auth-context"

// Null means no run has reached that stage yet -- "0%" would misleadingly
// imply a real rate of zero rather than "not computed."
function formatRate(rate: number | null) {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`
}

export function DashboardPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"

  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: fetchDashboardStats,
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          {isAdmin ? "Across every analyst's runs." : "Across your runs."}
        </p>
      </div>

      {isLoading || !stats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Samples processed"
            value={stats.total_samples_processed}
            icon={<FlaskConical className="size-5" />}
          />
          <StatTile
            label="Identification rate"
            value={formatRate(stats.identification_rate)}
            icon={<CheckCircle2 className="size-5" />}
          />
          <StatTile
            label="QC pass rate"
            value={formatRate(stats.qc_pass_rate)}
            icon={<ShieldCheck className="size-5" />}
          />
          <StatTile
            label="Pending review"
            value={stats.pending_review_count}
            icon={<AlertTriangle className="size-5" />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Species breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading || !stats ? (
              <Skeleton className="h-56 w-full" />
            ) : (
              <SpeciesDonut entries={stats.species_breakdown} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quality score distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading || !stats ? (
              <Skeleton className="h-56 w-full" />
            ) : (
              <QualityHistogram buckets={stats.quality_score_histogram} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
