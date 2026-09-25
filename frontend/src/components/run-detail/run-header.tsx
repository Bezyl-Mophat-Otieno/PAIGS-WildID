import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil, Play } from "lucide-react"
import { toast } from "sonner"
import { Link } from "react-router-dom"
import { executeRun, renameRun } from "@/api/runs"
import { RunStatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { runQueryKey } from "@/hooks/use-run"
import { useUserLookup } from "@/hooks/use-user-lookup"
import { getErrorMessage } from "@/lib/errors"
import type { RunDetail } from "@/types/api"

export function RunHeader({ run, isOwner }: { readonly run: RunDetail; readonly isOwner: boolean }) {
  const queryClient = useQueryClient()
  const { byId } = useUserLookup()
  const owner = byId.get(run.owner_id)

  const neverExecuted = run.status === "in_progress" && run.current_stage === "import"

  const executeMutation = useMutation({
    mutationFn: () => executeRun(run.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: runQueryKey(run.id) }),
    onError: (error) => toast.error(getErrorMessage(error, "Couldn't run this pipeline.")),
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{run.sample_id}</h1>
          {isOwner && <RenameDialog runId={run.id} currentLabel={run.sample_id} />}
        </div>
        <div className="flex items-center gap-2">
          {neverExecuted && isOwner && (
            <Button onClick={() => executeMutation.mutate()} disabled={executeMutation.isPending}>
              <Play className="size-4" />
              {executeMutation.isPending ? "Running..." : "Run pipeline"}
            </Button>
          )}
          {isOwner && (
            <Button variant="outline" asChild>
              <Link to={`/runs/${run.id}/rerun`}>Rerun with new config</Link>
            </Button>
          )}
        </div>
      </div>
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <RunStatusBadge status={run.status} />
        <span>Created {new Date(run.created_at).toLocaleString()}</span>
        {owner && <span>Owner: {owner.email}</span>}
        {run.rerun_of && (
          <Link to={`/runs/${run.rerun_of}`} className="text-primary hover:underline">
            Rerun of another run
          </Link>
        )}
      </div>
    </div>
  )
}

function RenameDialog({ runId, currentLabel }: { readonly runId: string; readonly currentLabel: string }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState(currentLabel)
  const [open, setOpen] = useState(false)

  const mutation = useMutation({
    mutationFn: () => renameRun(runId, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: runQueryKey(runId) })
      setOpen(false)
    },
    onError: (error) => toast.error(getErrorMessage(error, "Couldn't rename this run.")),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) setValue(currentLabel)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Rename run">
          <Pencil className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename run</DialogTitle>
        </DialogHeader>
        <Input value={value} onChange={(e) => setValue(e.target.value)} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || value.trim().length === 0}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
