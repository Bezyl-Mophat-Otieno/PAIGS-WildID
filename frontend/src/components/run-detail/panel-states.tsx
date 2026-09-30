import { AlertCircle, CircleDashed, Clock, Loader2 } from "lucide-react"

export function PendingPanel() {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-center text-sm">
      <Clock className="size-6" />
      This stage hasn't run yet.
    </div>
  )
}

// Only Stage 9 (BLAST) with blast.mode="remote" actually sits in this
// state today -- a real NCBI search running in the background (see
// CLAUDE.md's Stage 9 section), not blocking the request that started
// it. GET /runs/{id}'s existing poll picks up the eventual completed/
// failed transition the same way it already does for every other stage.
export function RunningPanel({ message }: { readonly message: string }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-center text-sm">
      <Loader2 className="text-primary size-6 animate-spin" />
      {message}
    </div>
  )
}

export function SkippedPanel({ reason }: { readonly reason: string }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-center text-sm">
      <CircleDashed className="size-6" />
      <p>Skipped -- not applicable to this run.</p>
      <p className="max-w-sm">{reason}</p>
    </div>
  )
}

export function ErrorPanel({ message }: { readonly message: string }) {
  return (
    <div className="text-status-critical flex flex-col items-center gap-2 py-16 text-center text-sm">
      <AlertCircle className="size-6" />
      {message}
    </div>
  )
}
