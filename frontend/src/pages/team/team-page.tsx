import { useMemo } from "react"
import { DataTable } from "@/components/data-table/data-table"
import { Skeleton } from "@/components/ui/skeleton"
import { useUserLookup } from "@/hooks/use-user-lookup"
import { InviteUserDialog } from "@/pages/team/invite-user-dialog"
import { buildUserColumns } from "@/pages/team/user-columns"

export function TeamPage() {
  const { data: users, byId, isLoading } = useUserLookup()

  const columns = useMemo(() => buildUserColumns(byId), [byId])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Team</h1>
          <p className="text-muted-foreground text-sm">Everyone with access to PAIGS WildID.</p>
        </div>
        <InviteUserDialog />
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <DataTable
          columns={columns}
          data={users ?? []}
          searchPlaceholder="Search by email..."
          emptyState={<p className="text-muted-foreground text-sm">No users yet.</p>}
        />
      )}
    </div>
  )
}
