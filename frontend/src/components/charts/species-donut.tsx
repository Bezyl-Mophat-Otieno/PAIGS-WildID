import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import { buildSpeciesBreakdown } from "@/lib/species-breakdown"

// Categorical hues 1-3 are the only ones validated for an all-pairs chart
// (every slice sits beside every other) -- the dataviz skill's cap, which
// is exactly why DESIGN.md caps this donut at 3 + "Other" rather than
// showing every species. "Other" gets a de-emphasis gray, never a 4th hue.
const SLICE_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)"]
const OTHER_COLOR = "var(--muted-foreground)"

export function SpeciesDonut({
  entries,
}: {
  readonly entries: { species: string; count: number }[]
}) {
  const slices = buildSpeciesBreakdown(entries)

  if (slices.length === 0) {
    return (
      <p className="text-muted-foreground flex h-56 items-center justify-center text-sm">
        No PASS identifications yet.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="h-56 w-full sm:w-56 sm:shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="count"
              nameKey="species"
              innerRadius="55%"
              outerRadius="85%"
              paddingAngle={slices.length > 1 ? 2 : 0}
              stroke="none"
              isAnimationActive={false}
              label={({ percent }) => `${Math.round((percent ?? 0) * 100)}%`}
              labelLine={false}
            >
              {slices.map((slice, index) => (
                <Cell
                  key={slice.species}
                  fill={slice.isOther ? OTHER_COLOR : SLICE_COLORS[index]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value, _name, entry) => [
                `${value} (${entry.payload.percentage.toFixed(1)}%)`,
                entry.payload.species,
              ]}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                color: "var(--popover-foreground)",
                fontSize: 13,
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      {/* Text-equivalent of the chart -- identity never rides on hue alone. */}
      <ul className="flex flex-1 flex-col gap-2">
        {slices.map((slice, index) => (
          <li key={slice.species} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{
                  backgroundColor: slice.isOther ? OTHER_COLOR : SLICE_COLORS[index],
                }}
              />
              <span className="truncate italic">{slice.species}</span>
            </span>
            <span className="text-muted-foreground shrink-0 tabular-nums">
              {slice.count} ({slice.percentage.toFixed(0)}%)
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
