import {
  columnFilteringFeature,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowSortingFeature,
  tableFeatures,
} from "@tanstack/react-table"

// TanStack Table v9 registers row models/behaviors as explicit feature slots
// rather than table constructor options (v8's getCoreRowModel()/etc) --
// one shared registration, reused by every sortable/filterable list in the
// app (runs, reports, config, reference versions -- DESIGN.md's TanStack
// Table row), since the feature set itself doesn't vary by data type.
export const tableFeatureSet = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
})
