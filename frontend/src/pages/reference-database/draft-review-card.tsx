import { useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import { discardReferenceDraft, publishReferenceDraft } from "@/api/reference-database"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getErrorMessage } from "@/lib/errors"
import type { ReferenceDatabaseDraft } from "@/types/api"

const publishFormSchema = z.object({
  version: z.string().min(1, "Version label is required"),
})
type PublishFormValues = z.infer<typeof publishFormSchema>

function PublishDraftDialog({ draft }: { readonly draft: ReferenceDatabaseDraft }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const form = useForm<PublishFormValues>({
    resolver: zodResolver(publishFormSchema),
    defaultValues: { version: `bold-${draft.taxon.toLowerCase().replace(/\s+/g, "-")}-v1` },
  })

  const mutation = useMutation({
    mutationFn: (values: PublishFormValues) => publishReferenceDraft(draft.id, values.version),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["reference-database"] })
      toast.success(`Published reference database ${result.version} -- now active.`)
      setOpen(false)
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (mutation.isPending) return
        setOpen(next)
        if (!next) mutation.reset()
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">
          <CheckCircle2 className="size-4" />
          Publish
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish this draft</DialogTitle>
          <DialogDescription>
            This immediately replaces the active reference database used for every future BLAST
            search. Make sure you've reviewed the species and BIN flags below first.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            className="flex flex-col gap-4"
          >
            {mutation.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {getErrorMessage(mutation.error, "Couldn't publish this draft.")}
                </AlertDescription>
              </Alert>
            )}
            <FormField
              control={form.control}
              name="version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Version label</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Publishing..." : "Publish"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

function DiscardDraftDialog({ draft }: { readonly draft: ReferenceDatabaseDraft }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => discardReferenceDraft(draft.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reference-database", "drafts"] })
      toast.success(`Discarded the "${draft.taxon}" draft.`)
      setOpen(false)
    },
  })

  return (
    <Dialog open={open} onOpenChange={mutation.isPending ? undefined : setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Discard
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Discard this draft?</DialogTitle>
          <DialogDescription>
            Nothing was ever published or made active -- this just removes "{draft.taxon}" from
            your pending review list. You can fetch it again later if you change your mind.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Discarding..." : "Discard"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DraftReviewCard({ draft }: { readonly draft: ReferenceDatabaseDraft }) {
  const { summary } = draft
  const inconsistentSpecies = summary.species.filter((s) => !s.bin_consistent)

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-base">{draft.taxon}</CardTitle>
          <p className="text-muted-foreground text-xs">
            Fetched {new Date(draft.fetched_at).toLocaleString()} from BOLD ({draft.marker})
          </p>
        </div>
        {draft.status === "pending_review" && (
          <div className="flex shrink-0 gap-2">
            <DiscardDraftDialog draft={draft} />
            <PublishDraftDialog draft={draft} />
          </div>
        )}
        {draft.status !== "pending_review" && (
          <Badge variant={draft.status === "published" ? "default" : "secondary"}>
            {draft.status === "published" ? `Published as ${draft.published_as_version}` : "Discarded"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="text-muted-foreground flex gap-4 text-sm">
          <span>{summary.total_fetched} record(s) fetched</span>
          <span>{summary.total_kept} kept</span>
          <span>{summary.species.length} species</span>
        </div>

        {Object.keys(summary.drop_reasons).length > 0 && (
          <div className="text-muted-foreground text-xs">
            Dropped:{" "}
            {Object.entries(summary.drop_reasons)
              .map(([reason, count]) => `${count} (${reason})`)
              .join(", ")}
          </div>
        )}

        {summary.total_kept_at_lower_rank > 0 && (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertDescription>
              {summary.total_kept_at_lower_rank} record(s) were only identified to genus/family
              level, not a real species -- allowed in because "Allow lower-rank identifications"
              was selected for this fetch. These are a materially less trustworthy answer-key
              entry (marked below); review carefully before publishing.
            </AlertDescription>
          </Alert>
        )}

        {summary.species_sharing_a_bin.length > 0 && (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertDescription>
              These species share a BIN with each other -- usually a sign of a misidentification or
              a synonym, worth a closer look before publishing:{" "}
              {summary.species_sharing_a_bin.map((group) => group.join(" / ")).join("; ")}
            </AlertDescription>
          </Alert>
        )}

        {inconsistentSpecies.length > 0 && (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertDescription>
              {inconsistentSpecies.length} species' own records split across more than one BIN --
              the DNA and the name may not agree. Check these before publishing.
            </AlertDescription>
          </Alert>
        )}

        {summary.species.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Species</TableHead>
                <TableHead className="text-right">Kept</TableHead>
                <TableHead className="text-right">Dropped</TableHead>
                <TableHead>BIN(s)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.species.map((s) => (
                <TableRow key={s.species}>
                  <TableCell className="italic">
                    {s.species}
                    {s.identification_rank !== "species" && (
                      <Badge variant="destructive" className="ml-2 not-italic">
                        {s.identification_rank}-level only
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{s.kept_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.dropped_count}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground text-xs">
                        {Array.from(new Set(s.bins)).join(", ") || "—"}
                      </span>
                      {!s.bin_consistent && (
                        <AlertTriangle className="text-status-critical size-3.5 shrink-0" />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
