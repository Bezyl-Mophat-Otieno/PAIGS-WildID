import { useQuery } from "@tanstack/react-query"
import { listUsers } from "@/api/admin"
import { useAuth } from "@/context/auth-context"

// RunRead carries owner_id but never an owner name/email (DESIGN.md's
// role-based behavior section) -- an admin's all-runs view has to join
// against GET /admin/users client-side. Centralized here so every screen
// that lists runs across users shares one lookup instead of re-fetching it.
export function useUserLookup() {
  const { user } = useAuth()

  const query = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listUsers,
    enabled: user?.role === "admin",
    staleTime: 5 * 60 * 1000,
  })

  const byId = new Map((query.data ?? []).map((u) => [u.id, u]))

  return { ...query, byId }
}
