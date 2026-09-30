import { useEffect, useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, Database } from "lucide-react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import { listConfig } from "@/api/config"
import { createReferenceDraft, listSuggestedTaxa } from "@/api/reference-database"
import { ConfigValueControl } from "@/components/config/config-value-control"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
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
import { cn } from "cn"
import { toFieldName } from "@/lib/config-groups"
import { getErrorMessage } from "@/lib/errors"
import type { ConfigItem } from "@/types/api"

const formSchema = z.object({
  taxon: z.string().min(1, "Enter a taxon name"),
  thresholds: z.record(z.string(), z.union([z.number(), z.string()])),
})

type FormValues = z.infer<typeof formSchema>

function buildThresholdDefaults(items: ConfigItem[]) {
  return Object.fromEntries(items.map((item) => [toFieldName(item.key), item.value]))
}

export function FetchBoldDialog() {
  const [open, setOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [thresholdsInitialized, setThresholdsInitialized] = useState(false)
  const queryClient = useQueryClient()

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { taxon: "", thresholds: {} },
  })

  // Convenience suggestions only -- BOLD's own query API (behind
  // createReferenceDraft) accepts any taxon it recognizes, not just
  // these. "Selectable from a list, or add your own -- no limitation."
  const suggestedQuery = useQuery({
    queryKey: ["reference-database", "suggested-taxa"],
    queryFn: listSuggestedTaxa,
    enabled: open,
  })

  // The same global config catalog every Run threshold comes from --
  // bold_fetch.* entries specifically (see app.configuration.catalog).
  // Reusing GET /config (rather than hardcoding defaults/bounds/choices
  // here) means this dialog can never silently drift out of sync with
  // the real, currently-effective global defaults.
  const configQuery = useQuery({ queryKey: ["config"], queryFn: listConfig, enabled: open })
  const boldFetchItems = (configQuery.data ?? []).filter((item) => item.stage_type === "bold_fetch")

  useEffect(() => {
    if (boldFetchItems.length > 0 && !thresholdsInitialized) {
      form.setValue("thresholds", buildThresholdDefaults(boldFetchItems))
      setThresholdsInitialized(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boldFetchItems.length, thresholdsInitialized])

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const byParam: Record<string, number | string> = {}
      for (const item of boldFetchItems) {
        byParam[item.param_name] = values.thresholds[toFieldName(item.key)]
      }
      return createReferenceDraft({
        taxon: values.taxon.trim(),
        max_records_per_species: byParam.max_records_per_species as number | undefined,
        min_sequence_length: byParam.min_sequence_length as number | undefined,
        max_n_proportion: byParam.max_n_proportion as number | undefined,
        require_species_level: byParam.require_species_level as string | undefined,
      })
    },
    onSuccess: (draft) => {
      queryClient.invalidateQueries({ queryKey: ["reference-database", "drafts"] })
      toast.success(
        `Fetched ${draft.summary.total_kept} candidate record(s) for "${draft.taxon}" -- review before publishing.`
      )
      setOpen(false)
      form.reset({ taxon: "", thresholds: {} })
      setThresholdsInitialized(false)
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (mutation.isPending) return
        setOpen(next)
        if (!next) {
          form.reset({ taxon: "", thresholds: {} })
          setThresholdsInitialized(false)
          mutation.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Database className="size-4" />
          Fetch from BOLD
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Fetch candidate records from BOLD</DialogTitle>
          <DialogDescription>
            This only creates a draft for review -- nothing becomes searchable until you explicitly
            publish it below.
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
                  {getErrorMessage(mutation.error, "Couldn't fetch from BOLD.")}
                </AlertDescription>
              </Alert>
            )}

            <FormField
              control={form.control}
              name="taxon"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Taxon name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Panthera, Felidae, Panthera leo" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {suggestedQuery.data && suggestedQuery.data.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <span className="text-muted-foreground text-xs">Or pick a suggestion</span>
                <div className="flex flex-wrap gap-1.5">
                  {suggestedQuery.data.map((taxon) => (
                    <Badge
                      key={taxon}
                      variant="outline"
                      className="hover:bg-accent cursor-pointer"
                      onClick={() => form.setValue("taxon", taxon, { shouldValidate: true })}
                    >
                      {taxon}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {boldFetchItems.length > 0 && (
              <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
                <CollapsibleTrigger className="text-muted-foreground flex w-full items-center justify-between text-left text-sm font-medium">
                  <span>Filters (species-level ID, quality floor, per-species cap)</span>
                  <ChevronDown
                    className={cn("size-4 shrink-0 transition-transform", advancedOpen && "rotate-180")}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-3 flex flex-col gap-4">
                  {boldFetchItems.map((item) => (
                    <FormField
                      key={item.key}
                      control={form.control}
                      name={`thresholds.${toFieldName(item.key)}`}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel
                            className={cn(
                              item.key === "bold_fetch.require_species_level" &&
                                field.value === "allow_lower_rank" &&
                                "text-status-critical"
                            )}
                          >
                            {item.label}
                          </FormLabel>
                          <FormControl>
                            <ConfigValueControl
                              item={item}
                              value={field.value as number | string}
                              onChange={field.onChange}
                              onBlur={field.onBlur}
                            />
                          </FormControl>
                          <p className="text-muted-foreground text-xs">{item.description}</p>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                </CollapsibleContent>
              </Collapsible>
            )}

            <DialogFooter>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Fetching..." : "Fetch"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
