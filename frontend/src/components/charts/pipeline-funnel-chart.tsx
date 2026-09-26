import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { FunnelPoint } from "@/lib/pipeline-funnel"

const FORWARD_COLOR = "var(--chart-1)"
const REVERSE_COLOR = "var(--chart-2)"
const MERGED_COLOR = "var(--chart-3)"

export function PipelineFunnelChart({ points }: { readonly points: FunnelPoint[] }) {
  const hasForward = points.some((p) => p.forward !== undefined)
  const hasReverse = points.some((p) => p.reverse !== undefined)
  const hasMerged = points.some((p) => p.merged !== undefined)

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="stage"
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <YAxis
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            width={40}
            unit=" bp"
          />
          <Tooltip
            contentStyle={{
              background: "var(--popover)",
              borderColor: "var(--border)",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--popover-foreground)" }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {hasForward && (
            <Bar
              dataKey="forward"
              name="Forward"
              fill={FORWARD_COLOR}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
          {hasReverse && (
            <Bar
              dataKey="reverse"
              name="Reverse"
              fill={REVERSE_COLOR}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
          {hasMerged && (
            <Bar
              dataKey="merged"
              name="Sequence"
              fill={MERGED_COLOR}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
