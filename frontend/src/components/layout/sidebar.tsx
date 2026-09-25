import { NavLink } from "react-router-dom"
import { Microscope } from "lucide-react"
import { cn } from "cn"
import { NAV_ITEMS } from "@/components/layout/nav-items"
import { useAuth } from "@/context/auth-context"

export function Sidebar() {
  const { user } = useAuth()

  const items = NAV_ITEMS.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role))
  )

  return (
    <aside className="bg-sidebar text-sidebar-foreground flex w-64 shrink-0 flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <Microscope className="text-sidebar-primary size-6" />
        <span className="text-lg font-semibold">PAIGS WildID</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-3">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                isActive && "bg-sidebar-accent text-sidebar-accent-foreground"
              )
            }
          >
            <item.icon className="size-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
