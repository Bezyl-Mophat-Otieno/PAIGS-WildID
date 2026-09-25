import { AlertCircle, CircleDashed, Clock } from "lucide-react"

export function PendingPanel() {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-center text-sm">
      <Clock className="size-6" />
      This stage hasn't run yet.
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
