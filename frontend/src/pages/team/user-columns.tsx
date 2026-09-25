import { createColumnHelper } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { tableFeatureSet } from "@/lib/table-features"
import type { User } from "@/types/api"

const columnHelper = createColumnHelper<typeof tableFeatureSet, User>()

export function buildUserColumns(byId: Map<string, User>) {
  return columnHelper.columns([
    columnHelper.accessor("email", {
      header: "Email",
      cell: (info) => <span className="font-medium">{info.getValue()}</span>,
    }),
    columnHelper.accessor("role", {
      header: "Role",
      cell: (info) => <Badge variant="outline" className="capitalize">{info.getValue()}</Badge>,
    }),
    columnHelper.accessor("is_active", {
      header: "Status",
      cell: (info) => (info.getValue() ? "Active" : "Inactive"),
    }),
    columnHelper.accessor((user) => byId.get(user.invited_by_id ?? "")?.email ?? "—", {
      id: "invited_by",
      header: "Invited by",
    }),
    columnHelper.accessor("created_at", {
      header: "Joined",
      cell: (info) => new Date(info.getValue()).toLocaleDateString(),
    }),
  ])
}
