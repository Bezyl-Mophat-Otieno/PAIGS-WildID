import { createColumnHelper } from "@tanstack/react-table"
import { RunStatusBadge } from "@/components/status-badge"
import { tableFeatureSet } from "@/lib/table-features"
import { ReportDownloadCell } from "@/pages/reports/report-download-cell"
import type { Run, User } from "@/types/api"

const columnHelper = createColumnHelper<typeof tableFeatureSet, Run>()

export function buildReportColumns(options: {
  readonly isAdmin: boolean
  readonly ownerById: Map<string, User>
}) {
  return columnHelper.columns([
    columnHelper.accessor("sample_id", {
      header: "Sample",
      cell: (info) => <span className="font-medium">{info.getValue()}</span>,
    }),
    columnHelper.accessor("status", {
      header: "Status",
      cell: (info) => <RunStatusBadge status={info.getValue()} />,
    }),
    ...(options.isAdmin
      ? [
          columnHelper.accessor(
            (run) => options.ownerById.get(run.owner_id)?.email ?? run.owner_id,
            { id: "owner", header: "Owner" }
          ),
        ]
      : []),
    columnHelper.accessor("created_at", {
      header: "Created",
      cell: (info) => new Date(info.getValue()).toLocaleString(),
    }),
    columnHelper.display({
      id: "report",
      header: "Report",
      cell: ({ row }) => (
        <ReportDownloadCell
          runId={row.original.id}
          sampleId={row.original.sample_id}
          likelyAvailable={row.original.status === "completed"}
        />
      ),
    }),
  ])
}
