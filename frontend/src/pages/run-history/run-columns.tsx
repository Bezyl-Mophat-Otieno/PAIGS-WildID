import { createColumnHelper } from "@tanstack/react-table"
import { RunStatusBadge } from "@/components/status-badge"
import { STAGE_LABELS } from "@/lib/stages"
import { tableFeatureSet } from "@/lib/table-features"
import type { Run, User } from "@/types/api"

const columnHelper = createColumnHelper<typeof tableFeatureSet, Run>()

export function buildRunColumns(options: {
  readonly isAdmin: boolean
  readonly ownerById: Map<string, User>
}) {
  // Built as one array literal (with a conditional spread for the
  // admin-only column) rather than assembled via push -- columnHelper's own
  // `.columns()` needs the full literal in one call to infer each column's
  // individual value type instead of widening them all to the first one's.
  return columnHelper.columns([
    columnHelper.accessor("sample_id", {
      header: "Sample",
      cell: (info) => <span className="font-medium">{info.getValue()}</span>,
    }),
    columnHelper.accessor("status", {
      header: "Status",
      cell: (info) => <RunStatusBadge status={info.getValue()} />,
    }),
    columnHelper.accessor("current_stage", {
      header: "Current stage",
      cell: (info) => STAGE_LABELS[info.getValue()],
    }),
    // Owner is only worth a column in the admin's cross-tenant view -- an
    // analyst's own list is implicitly all "you" (DESIGN.md's role section).
    ...(options.isAdmin
      ? [
          columnHelper.accessor(
            (run) => options.ownerById.get(run.owner_id)?.email ?? run.owner_id,
            { id: "owner", header: "Owner" }
          ),
        ]
      : []),
    columnHelper.accessor((run) => run.original_filenames.length, {
      id: "reads",
      header: "Reads",
      cell: (info) => (info.getValue() === 2 ? "Forward + Reverse" : "Single read"),
    }),
    columnHelper.accessor("created_at", {
      header: "Created",
      cell: (info) => new Date(info.getValue()).toLocaleString(),
    }),
  ])
}
