import { useEffect, useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertCircle, RotateCcw } from "lucide-react"
import { useForm } from "react-hook-form"
import { useParams } from "react-router-dom"
import { z } from "zod"
import { listConfig } from "@/api/config"
import { listRuns, rerunRun } from "@/api/runs"
import { ConfigOverridesSection } from "@/components/new-analysis/config-overrides-section"
import { RunStatusBadge } from "@/components/status-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useEffectiveThresholds } from "@/hooks/use-effective-thresholds"
import { useRun } from "@/hooks/use-run"
import { useStage } from "@/hooks/use-stage"
import { toFieldName } from "@/lib/config-groups"
import { getErrorMessage } from "@/lib/errors"
import { buildThresholdDiff, mergeSourceThresholds } from "@/lib/rerun-prefill"
import { deriveDefaultSampleId } from "@/lib/sample-id"
import { stageHasRun } from "@/lib/stages"
import { RunSummaryCard } from "@/pages/rerun/run-summary-card"
import { ThresholdDiffTable } from "@/pages/rerun/threshold-diff-table"
import type { ConfigItem, IdentificationOutput } from "@/types/api"

const formSchema = z.object({
  sample_id: z.string().min(1, "Sample label is required"),
  thresholds: z.record(z.string(), z.number()),
})

type FormValues = z.infer<typeof formSchema>

function buildThresholdDefaults(items: ConfigItem[]) {
  return Object.fromEntries(items.map((item) => [toFieldName(item.key), item.value]))
}

export function RerunPage() {
  const { runId: sourceId } = useParams<{ runId: string }>()
  const queryClient = useQueryClient()

  const [comparisonRunId, setComparisonRunId] = useState<string | null>(null)
  const [sampleIdEdited, setSampleIdEdited] = useState(false)
  const [thresholdsInitialized, setThresholdsInitialized] = useState(false)

  const { data: sourceRun, isLoading: sourceLoading } = useRun(sourceId)
  const { data: comparisonRun } = useRun(comparisonRunId ?? undefined)
  const { data: allRuns } = useQuery({ queryKey: ["runs"], queryFn: listRuns })
  const configQuery = useQuery({ queryKey: ["config"], queryFn: listConfig })

  const sourceStages = sourceRun?.stages ?? []
  const comparisonStages = comparisonRun?.stages ?? []
  const sourceEffective = useEffectiveThresholds(sourceId ?? "", sourceStages)
  const comparisonEffective = useEffectiveThresholds(comparisonRunId ?? "", comparisonStages)

  const sourceIdentificationQuery = useStage(
    sourceId ?? "",
    "identification",
    stageHasRun(sourceStages, "identification")
  )
  const comparisonIdentificationQuery = useStage(
    comparisonRunId ?? "",
    "identification",
    stageHasRun(comparisonStages, "identification")
  )

  const priorReruns = (allRuns ?? [])
    .filter((r) => r.rerun_of === sourceId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { sample_id: "", thresholds: {} },
  })

  // Prefill from the SOURCE run's own effective thresholds, not current
  // global defaults -- config can drift between when the source ran and
  // now (DESIGN.md's Rerun screen). A key the source never reached falls
  // back to the current catalog default inside mergeSourceThresholds.
  useEffect(() => {
    if (sourceRun && configQuery.data && !sourceEffective.isLoading && !thresholdsInitialized) {
      const merged = mergeSourceThresholds(configQuery.data, sourceEffective.rows)
      form.reset({
        sample_id: form.getValues("sample_id"),
        thresholds: buildThresholdDefaults(merged),
      })
      setThresholdsInitialized(true)
    }
  }, [sourceRun, configQuery.data, sourceEffective.isLoading, sourceEffective.rows, thresholdsInitialized, form])

  useEffect(() => {
    if (sampleIdEdited || !sourceRun) return
    form.setValue("sample_id", deriveDefaultSampleId(sourceRun.original_filenames))
  }, [sourceRun, sampleIdEdited, form])

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const dirtyThresholds = form.formState.dirtyFields.thresholds ?? {}
      const overrides: Record<string, number> = {}
      for (const item of configQuery.data ?? []) {
        const fieldName = toFieldName(item.key)
        if (dirtyThresholds[fieldName]) {
          overrides[item.key] = values.thresholds[fieldName]
        }
      }

      return rerunRun(sourceId!, {
        sample_id: values.sample_id,
        config_overrides: overrides,
        auto_execute: true,
      })
    },
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] })
      setComparisonRunId(detail.id)
    },
  })

  if (sourceLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!sourceRun) {
    return <p className="text-status-critical text-sm">This run couldn't be found.</p>
  }

  const diffRows =
    configQuery.data && comparisonRun
      ? buildThresholdDiff(configQuery.data, sourceEffective.rows, comparisonEffective.rows)
      : []

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Rerun {sourceRun.sample_id}</h1>
        <p className="text-muted-foreground text-sm">
          Reuses the same uploaded file(s) under a new configuration -- a brand-new Run, side by
          side with the original.
        </p>
      </div>

      {comparisonRun ? (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <RunSummaryCard
              title="Source"
              run={sourceRun}
              identification={sourceIdentificationQuery.data?.output as IdentificationOutput | undefined}
            />
            <RunSummaryCard
              title="Rerun"
              run={comparisonRun}
              identification={
                comparisonIdentificationQuery.data?.output as IdentificationOutput | undefined
              }
            />
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Threshold differences</CardTitle>
            </CardHeader>
            <CardContent>
              <ThresholdDiffTable rows={diffRows} />
            </CardContent>
          </Card>
          <Button variant="outline" className="self-start" onClick={() => setComparisonRunId(null)}>
            <RotateCcw className="size-4" />
            Configure another rerun
          </Button>
        </div>
      ) : (
        <>
          {priorReruns.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Previous reruns of this source</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {priorReruns.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setComparisonRunId(run.id)}
                    className="border-border hover:bg-muted flex items-center justify-between rounded-lg border p-3 text-left text-sm"
                  >
                    <span className="font-medium">{run.sample_id}</span>
                    <span className="flex items-center gap-3">
                      <span className="text-muted-foreground">
                        {new Date(run.created_at).toLocaleString()}
                      </span>
                      <RunStatusBadge status={run.status} />
                    </span>
                  </button>
                ))}
              </CardContent>
            </Card>
          )}

          <Form {...form}>
            <form onSubmit={form.handleSubmit((values) => mutation.mutate(values))} className="flex flex-col gap-6">
              {mutation.isError && (
                <Alert variant="destructive">
                  <AlertCircle className="size-4" />
                  <AlertTitle>Couldn't start this rerun</AlertTitle>
                  <AlertDescription>
                    {getErrorMessage(mutation.error, "Something went wrong. Please try again.")}
                  </AlertDescription>
                </Alert>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>Sample label</CardTitle>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="sample_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Sample ID</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            onChange={(e) => {
                              setSampleIdEdited(true)
                              field.onChange(e)
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              {configQuery.data && !sourceEffective.isLoading && (
                <ConfigOverridesSection
                  items={mergeSourceThresholds(configQuery.data, sourceEffective.rows)}
                  control={form.control}
                />
              )}

              <Button type="submit" disabled={mutation.isPending} className="self-start">
                {mutation.isPending ? "Running pipeline..." : "Start Rerun"}
              </Button>
            </form>
          </Form>
        </>
      )}
    </div>
  )
}
