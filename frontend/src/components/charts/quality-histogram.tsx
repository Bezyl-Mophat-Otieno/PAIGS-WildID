import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts"

// Sequential magnitude data gets one hue, not a categorical rainbow --
// the dataviz skill's default rule for "compare magnitude, low to high."
const SEQUENTIAL_FILL = "var(--chart-1)"

export function QualityHistogram({
  buckets,
}: {
  readonly buckets: { label: string; count: number }[]
}) {
  const total = buckets.reduce((sum, b) => sum + b.count, 0)

  if (total === 0) {
    return (
      <p className="text-muted-foreground flex h-56 items-center justify-center text-sm">
        No usability-checked runs yet.
      </p>
    )
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={buckets} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <YAxis hide allowDecimals={false} />
          <Bar
            dataKey="count"
            fill={SEQUENTIAL_FILL}
            radius={[4, 4, 0, 0]}
            maxBarSize={48}
            isAnimationActive={false}
          >
            <LabelList
              dataKey="count"
              position="top"
              style={{ fill: "var(--foreground)", fontSize: 12 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
