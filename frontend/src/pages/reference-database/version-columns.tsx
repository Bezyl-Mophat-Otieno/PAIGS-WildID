import { createColumnHelper } from "@tanstack/react-table"
import { CheckCircle2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { tableFeatureSet } from "@/lib/table-features"
import type { ReferenceDatabaseVersion } from "@/types/api"

const columnHelper = createColumnHelper<typeof tableFeatureSet, ReferenceDatabaseVersion>()

export const versionColumns = columnHelper.columns([
  columnHelper.accessor("version", {
    header: "Version",
    cell: (info) => (
      <div className="flex items-center gap-2">
        <span className="font-medium">{info.getValue()}</span>
        {info.row.original.is_active && (
          <Badge className="bg-status-good/10 text-status-good gap-1 border-transparent">
            <CheckCircle2 className="size-3" />
            Active
          </Badge>
        )}
      </div>
    ),
  }),
  columnHelper.accessor("sequence_count", {
    header: "Sequences",
  }),
  columnHelper.accessor("published_at", {
    header: "Published",
    cell: (info) => new Date(info.getValue()).toLocaleString(),
  }),
])
