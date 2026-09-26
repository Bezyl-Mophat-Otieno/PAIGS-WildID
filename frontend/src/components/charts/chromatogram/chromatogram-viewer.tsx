import { useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { colorForBase } from "@/lib/chromatogram-colors"
import type { ChromatogramData } from "@/types/api"

const VIEW_WIDTH = 1000
const TRACE_HEIGHT = 160
const RULER_HEIGHT = 30
const OVERVIEW_HEIGHT = 36
const ZOOM_STEPS = [20, 40, 80, 160, 320]

const KEPT_FILL = "var(--chart-1)"
const CUT_FILL = "var(--muted-foreground)"

function computeGlobalMax(trace: Record<string, number[]>) {
  let max = 0
  for (const values of Object.values(trace)) {
    for (const v of values) if (v > max) max = v
  }
  return max || 1
}

function buildPoints(
  values: number[],
  sampleStart: number,
  sampleEnd: number,
  maxValue: number
) {
  const range = sampleEnd - sampleStart || 1
  const points: string[] = []
  for (let s = sampleStart; s <= sampleEnd; s++) {
    const x = ((s - sampleStart) / range) * VIEW_WIDTH
    const y = TRACE_HEIGHT - (values[s] / maxValue) * TRACE_HEIGHT
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return points.join(" ")
}

// A cheap single-line envelope (max across all 4 channels, downsampled)
// for the overview strip -- the detail view above is where individual
// channels actually matter.
function buildOverviewEnvelope(trace: Record<string, number[]>, numSamples: number, buckets: number) {
  const channelArrays = Object.values(trace)
  const bucketSize = numSamples / buckets
  const values: number[] = new Array(buckets).fill(0)
  for (let b = 0; b < buckets; b++) {
    const start = Math.floor(b * bucketSize)
    const end = Math.floor((b + 1) * bucketSize)
    let m = 0
    for (const arr of channelArrays) {
      for (let s = start; s < end; s++) {
        if (arr[s] > m) m = arr[s]
      }
    }
    values[b] = m
  }
  return values
}

function nearestBaseIndex(peakLocations: number[], sampleIndex: number) {
  // peak_locations is monotonically non-decreasing (confirmed against the
  // real backend data) -- a linear scan is plenty fast for ~1-2k bases.
  let closest = 0
  let closestDistance = Infinity
  for (let i = 0; i < peakLocations.length; i++) {
    const distance = Math.abs(peakLocations[i] - sampleIndex)
    if (distance < closestDistance) {
      closestDistance = distance
      closest = i
    }
  }
  return closest
}

export function ChromatogramViewer({
  data,
  trimRange,
  initialPosition,
}: {
  readonly data: ChromatogramData
  readonly trimRange?: { start: number; end: number }
  readonly initialPosition?: number
}) {
  const baseCount = data.base_calls.length
  const [zoomIndex, setZoomIndex] = useState(2)
  const basesPerView = Math.min(ZOOM_STEPS[zoomIndex], baseCount)
  const [windowStart, setWindowStart] = useState(() =>
    Math.max(0, Math.min((initialPosition ?? 0) - Math.floor(basesPerView / 2), baseCount - basesPerView))
  )

  const globalMax = useMemo(() => computeGlobalMax(data.trace), [data.trace])
  const overview = useMemo(
    () => buildOverviewEnvelope(data.trace, data.num_samples, 400),
    [data.trace, data.num_samples]
  )

  const clampedStart = Math.max(0, Math.min(windowStart, Math.max(0, baseCount - basesPerView)))
  const windowEnd = Math.min(clampedStart + basesPerView - 1, baseCount - 1)

  const avgSpacing = data.num_samples / baseCount
  const padding = avgSpacing
  const sampleStart = Math.max(0, Math.round(data.peak_locations[clampedStart] - padding))
  const sampleEnd = Math.min(
    data.num_samples - 1,
    Math.round(data.peak_locations[windowEnd] + padding)
  )

  function pan(direction: 1 | -1) {
    const step = Math.max(1, Math.floor(basesPerView / 2))
    setWindowStart((prev) =>
      Math.max(0, Math.min(prev + direction * step, Math.max(0, baseCount - basesPerView)))
    )
  }

  function zoom(direction: 1 | -1) {
    setZoomIndex((prev) => Math.max(0, Math.min(prev + direction, ZOOM_STEPS.length - 1)))
  }

  function jumpToOverviewClick(event: React.MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - rect.left) / rect.width
    const sampleIndex = Math.round(fraction * data.num_samples)
    const baseIndex = nearestBaseIndex(data.peak_locations, sampleIndex)
    setWindowStart(Math.max(0, Math.min(baseIndex - Math.floor(basesPerView / 2), baseCount - basesPerView)))
  }

  // Trim boundary shading, only if this viewer was opened with that context
  // (e.g. from the Trim panel) -- same kept/cut convention as the trim
  // quality chart, so the two read as one visual language.
  const trimSamples = trimRange
    ? {
        start: data.peak_locations[Math.min(trimRange.start, baseCount - 1)] ?? 0,
        end: data.peak_locations[Math.min(trimRange.end, baseCount - 1)] ?? data.num_samples - 1,
      }
    : undefined

  function toDetailX(sample: number) {
    return ((sample - sampleStart) / (sampleEnd - sampleStart || 1)) * VIEW_WIDTH
  }
  function toOverviewX(sample: number) {
    return (sample / data.num_samples) * VIEW_WIDTH
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => pan(-1)} disabled={clampedStart === 0}>
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => pan(1)}
            disabled={clampedStart + basesPerView >= baseCount}
          >
            <ChevronRight className="size-4" />
          </Button>
          <span className="text-muted-foreground ml-2 text-xs">
            Bases {clampedStart}
            {"–"}
            {windowEnd} of {baseCount}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            onClick={() => zoom(-1)}
            disabled={zoomIndex === 0}
            aria-label="Zoom in"
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => zoom(1)}
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            aria-label="Zoom out"
          >
            <ZoomOut className="size-4" />
          </Button>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${TRACE_HEIGHT + RULER_HEIGHT}`}
        className="border-border w-full rounded-md border"
        preserveAspectRatio="none"
      >
        {trimSamples && (
          <>
            <rect
              x={0}
              y={0}
              width={VIEW_WIDTH}
              height={TRACE_HEIGHT}
              fill={CUT_FILL}
              opacity={0.06}
            />
            <rect
              x={Math.max(0, toDetailX(trimSamples.start))}
              y={0}
              width={Math.max(0, toDetailX(trimSamples.end) - toDetailX(trimSamples.start))}
              height={TRACE_HEIGHT}
              fill={KEPT_FILL}
              opacity={0.08}
            />
          </>
        )}
        {Object.entries(data.trace).map(([base, values]) => (
          <polyline
            key={base}
            points={buildPoints(values, sampleStart, sampleEnd, globalMax)}
            fill="none"
            stroke={colorForBase(base)}
            strokeWidth={1.5}
          />
        ))}
        {Array.from({ length: windowEnd - clampedStart + 1 }, (_, i) => clampedStart + i).map((i) => {
          const x = toDetailX(data.peak_locations[i])
          const base = data.base_calls[i]
          return (
            <g key={i}>
              <line
                x1={x}
                x2={x}
                y1={TRACE_HEIGHT}
                y2={TRACE_HEIGHT + 6}
                stroke={colorForBase(base)}
                strokeWidth={1}
              />
              <text
                x={x}
                y={TRACE_HEIGHT + 20}
                textAnchor="middle"
                fontSize={13}
                fontFamily="ui-monospace, monospace"
                fill={colorForBase(base)}
              >
                {base}
              </text>
            </g>
          )
        })}
      </svg>

      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${OVERVIEW_HEIGHT}`}
        className="border-border bg-muted/30 w-full cursor-pointer rounded-md border"
        preserveAspectRatio="none"
        onClick={jumpToOverviewClick}
      >
        {trimSamples && (
          <>
            <rect x={0} y={0} width={VIEW_WIDTH} height={OVERVIEW_HEIGHT} fill={CUT_FILL} opacity={0.06} />
            <rect
              x={toOverviewX(trimSamples.start)}
              y={0}
              width={toOverviewX(trimSamples.end) - toOverviewX(trimSamples.start)}
              height={OVERVIEW_HEIGHT}
              fill={KEPT_FILL}
              opacity={0.1}
            />
          </>
        )}
        <polyline
          points={overview
            .map(
              (v, i) =>
                `${((i / overview.length) * VIEW_WIDTH).toFixed(1)},${(OVERVIEW_HEIGHT - (v / globalMax) * OVERVIEW_HEIGHT).toFixed(1)}`
            )
            .join(" ")}
          fill="none"
          stroke="var(--muted-foreground)"
          strokeWidth={1}
        />
        <rect
          x={toOverviewX(sampleStart)}
          y={0}
          width={Math.max(2, toOverviewX(sampleEnd) - toOverviewX(sampleStart))}
          height={OVERVIEW_HEIGHT}
          fill="var(--foreground)"
          opacity={0.12}
          stroke="var(--foreground)"
          strokeWidth={1}
        />
      </svg>

      <div className="flex items-center gap-4 text-xs">
        {data.channel_order.map((base) => (
          <span key={base} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4" style={{ backgroundColor: colorForBase(base) }} />
            <span className="text-muted-foreground">{base}</span>
          </span>
        ))}
        {trimRange && (
          <span className="text-muted-foreground ml-auto">
            Blue = kept window, gray = trimmed away
          </span>
        )}
      </div>
    </div>
  )
}
