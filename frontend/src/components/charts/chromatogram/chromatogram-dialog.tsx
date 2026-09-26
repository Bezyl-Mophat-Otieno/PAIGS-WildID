import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Waves } from "lucide-react"
import { getChromatogram } from "@/api/runs"
import { ChromatogramViewer } from "@/components/charts/chromatogram/chromatogram-viewer"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import type { ReadSlotKey } from "@/types/api"

export function ChromatogramDialog({
  runId,
  slot,
  trimRange,
  initialPosition,
}: {
  readonly runId: string
  readonly slot: ReadSlotKey
  readonly trimRange?: { start: number; end: number }
  readonly initialPosition?: number
}) {
  const [open, setOpen] = useState(false)

  const query = useQuery({
    queryKey: ["runs", runId, "chromatogram", slot],
    queryFn: () => getChromatogram(runId, slot),
    enabled: open,
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Waves className="size-4" />
          View chromatogram
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="capitalize">{slot} read chromatogram</DialogTitle>
        </DialogHeader>
        {query.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : query.data ? (
          <ChromatogramViewer
            data={query.data}
            trimRange={trimRange}
            initialPosition={initialPosition}
          />
        ) : (
          <p className="text-status-critical text-sm">Couldn't load the chromatogram.</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
