import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts"

// Sequential blue for the kept window (a magnitude signal, per the dataviz
// skill's default); the trimmed-away edges get the de-emphasis gray, never
// a second hue -- there's nothing categorical here, just kept vs. cut.
const KEPT_COLOR = "var(--chart-1)"
const CUT_COLOR = "var(--muted-foreground)"

interface QualityPoint {
  position: number
  before: number | null
  kept: number | null
  after: number | null
}

function buildSegments(qualityScores: number[], trimStart: number, trimEnd: number): QualityPoint[] {
  return qualityScores.map((quality, position) => ({
    position,
    // Each point sits in exactly one segment except at the two boundaries,
    // which are duplicated into both neighbors so the line has no visual
    // gap at the cut itself.
    before: position <= trimStart ? quality : null,
    kept: position >= trimStart && position <= trimEnd ? quality : null,
    after: position >= trimEnd ? quality : null,
  }))
}

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload) return null
  const point = payload.find(
    (p): p is typeof p & { value: number } => typeof p.value === "number"
  )
  if (!point) return null
  return (
    <div className="bg-popover text-popover-foreground border-border rounded-md border px-2.5 py-1.5 text-xs shadow-sm">
      <p className="text-muted-foreground">Position {label}</p>
      <p className="font-medium">Quality {point.value}</p>
    </div>
  )
}

export function TrimQualityChart({
  qualityScores,
  trimStart,
  trimEnd,
  qualityThreshold,
}: {
  readonly qualityScores: number[]
  readonly trimStart: number
  readonly trimEnd: number
  readonly qualityThreshold: number
}) {
  const data = buildSegments(qualityScores, trimStart, trimEnd)

  return (
    <div className="flex flex-col gap-2">
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="position"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              label={{
                value: "Position (bp)",
                position: "insideBottom",
                offset: -2,
                fill: "var(--muted-foreground)",
                fontSize: 11,
              }}
            />
            <YAxis
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              width={28}
            />
            <ReferenceLine
              y={qualityThreshold}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              label={{
                value: `Q${qualityThreshold} cutoff`,
                position: "insideTopRight",
                fill: "var(--muted-foreground)",
                fontSize: 11,
              }}
            />
            <Area
              dataKey="kept"
              stroke={KEPT_COLOR}
              strokeWidth={2}
              fill={KEPT_COLOR}
              fillOpacity={0.1}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="before"
              stroke={CUT_COLOR}
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="after"
              stroke={CUT_COLOR}
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Tooltip content={ChartTooltip} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-muted-foreground text-xs">
        Kept window shown in blue ({trimStart}
        {"–"}
        {trimEnd} bp); trimmed-away edges in gray.
      </p>
    </div>
  )
}
