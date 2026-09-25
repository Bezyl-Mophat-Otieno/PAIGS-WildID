import { useState, type ReactNode } from "react"
import { flexRender, useTable, type ColumnDef, type RowData } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { tableFeatureSet } from "@/lib/table-features"

// Shared by every sortable/filterable list the app needs (runs, reports,
// config, reference versions -- DESIGN.md's tech stack row for TanStack
// Table) -- built once here rather than per-screen.
interface DataTableProps<TData extends RowData> {
  readonly columns: ColumnDef<typeof tableFeatureSet, TData>[]
  readonly data: TData[]
  readonly searchPlaceholder?: string
  readonly onRowClick?: (row: TData) => void
  readonly emptyState?: ReactNode
}

export function DataTable<TData extends RowData>({
  columns,
  data,
  searchPlaceholder = "Search...",
  onRowClick,
  emptyState,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<{ id: string; desc: boolean }[]>([])
  const [globalFilter, setGlobalFilter] = useState("")

  const table = useTable({
    features: tableFeatureSet,
    columns,
    data,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: "includesString",
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="relative max-w-sm">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder={searchPlaceholder}
          className="pl-9"
        />
      </div>
      <div className="border-border overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sortState = header.column.getIsSorted()
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          type="button"
                          className="hover:text-foreground flex items-center gap-1"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sortState === "asc" && <ArrowUp className="size-3.5" />}
                          {sortState === "desc" && <ArrowDown className="size-3.5" />}
                          {!sortState && <ArrowUpDown className="text-muted-foreground/50 size-3.5" />}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-32 text-center">
                  {emptyState ?? <span className="text-muted-foreground text-sm">No results.</span>}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={onRowClick ? "hover:bg-muted cursor-pointer" : undefined}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getAllCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
