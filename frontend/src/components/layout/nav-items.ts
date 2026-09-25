import type { LucideIcon } from "lucide-react"
import {
  Database,
  FileText,
  History,
  LayoutDashboard,
  Settings,
  Upload,
  Users,
} from "lucide-react"
import type { Role } from "@/types/api"

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  // Undefined = visible to every authenticated role.
  roles?: Role[]
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
  { label: "New Analysis", to: "/new-analysis", icon: Upload },
  { label: "Run History", to: "/runs", icon: History },
  { label: "Reports", to: "/reports", icon: FileText },
  { label: "Configuration", to: "/configuration", icon: Settings },
  { label: "Reference Database", to: "/reference-database", icon: Database },
  { label: "Team", to: "/team", icon: Users, roles: ["admin"] },
]
