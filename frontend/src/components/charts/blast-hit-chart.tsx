import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts"
import type { BlastHit } from "@/types/api"

const IDENTITY_COLOR = "var(--chart-1)"
const COVERAGE_COLOR = "var(--chart-2)"

interface HitPoint extends BlastHit {
  label: string
}

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload || payload.length === 0) return null
  const hit = payload[0]?.payload as HitPoint | undefined
  if (!hit) return null
  return (
    <div className="bg-popover text-popover-foreground border-border rounded-md border px-2.5 py-1.5 text-xs shadow-sm">
      <p className="font-medium italic">{hit.species}</p>
      <p className="text-muted-foreground">{label}</p>
      <p>
        Identity {hit.identity.toFixed(2)}% {"–"} Coverage {hit.coverage.toFixed(1)}%
      </p>
      <p className="text-muted-foreground">
        Bit score {hit.bit_score} {"–"} E-value {hit.evalue}
      </p>
    </div>
  )
}

// Stage 9/10's hit comparison (DESIGN.md): identity%/coverage% across the
// ranked BLAST hit list, with Stage 10's ambiguous-margin threshold drawn
// as a reference line -- makes an AMBIGUOUS verdict visually intuitive
// instead of two bare numbers in a table row.
export function BlastHitChart({
  hits,
  ambiguousMarginPct,
}: {
  readonly hits: BlastHit[]
  readonly ambiguousMarginPct?: number
}) {
  const data: HitPoint[] = hits.map((hit) => ({ ...hit, label: `#${hit.rank}` }))

  // ambiguous_margin_pct is a *gap* (top hit's identity minus the runner-up's),
  // not an absolute cutoff -- so the line that actually represents it sits at
  // (top hit's identity - margin). Any other hit's bar rising above that line
  // is within the margin of the top match (app.pipeline.identification.py's
  // own comparison, mirrored here rather than guessed).
  const marginCutoff =
    ambiguousMarginPct !== undefined && hits.length > 1
      ? hits[0].identity - ambiguousMarginPct
      : null

  return (
    <div className="flex flex-col gap-2">
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            />
            <YAxis
              domain={[0, 100]}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              width={36}
              unit="%"
            />
            {marginCutoff !== null && (
              <ReferenceLine
                y={marginCutoff}
                stroke="var(--status-warning)"
                strokeDasharray="4 4"
                label={{
                  value: "Ambiguous margin cutoff",
                  position: "insideTopLeft",
                  fill: "var(--status-warning)",
                  fontSize: 11,
                }}
              />
            )}
            <Tooltip content={ChartTooltip} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar
              dataKey="identity"
              name="Identity %"
              fill={IDENTITY_COLOR}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
            <Bar
              dataKey="coverage"
              name="Coverage %"
              fill={COVERAGE_COLOR}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {marginCutoff !== null && (
        <p className="text-muted-foreground text-xs">
          Any candidate other than the top hit whose identity bar rises above the dashed
          line is within the ambiguous margin ({ambiguousMarginPct} point
          {ambiguousMarginPct === 1 ? "" : "s"}) of the top match.
        </p>
      )}
    </div>
  )
}
