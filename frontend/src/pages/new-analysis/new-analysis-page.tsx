import { useEffect, useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertCircle } from "lucide-react"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { z } from "zod"
import { listConfig } from "@/api/config"
import { createRun, executeRun } from "@/api/runs"
import { ConfigOverridesSection } from "@/components/new-analysis/config-overrides-section"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { DualFileDropzone, type SlotFiles } from "@/components/upload/dual-file-dropzone"
import { toFieldName } from "@/lib/config-groups"
import { getErrorMessage } from "@/lib/errors"
import { deriveDefaultSampleId } from "@/lib/sample-id"
import type { ConfigItem } from "@/types/api"

const formSchema = z.object({
  sample_id: z.string().min(1, "Sample label is required"),
  thresholds: z.record(z.string(), z.number()),
})

type FormValues = z.infer<typeof formSchema>

function buildThresholdDefaults(items: ConfigItem[]) {
  return Object.fromEntries(items.map((item) => [toFieldName(item.key), item.value]))
}

export function NewAnalysisPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [files, setFiles] = useState<SlotFiles>({ forward: null, reverse: null })
  const [fileError, setFileError] = useState<string | null>(null)
  const [sampleIdEdited, setSampleIdEdited] = useState(false)
  const [thresholdsInitialized, setThresholdsInitialized] = useState(false)

  const configQuery = useQuery({ queryKey: ["config"], queryFn: listConfig })

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { sample_id: "", thresholds: {} },
  })

  // Threshold defaults arrive async from GET /config -- reset once so the
  // form's dirty-tracking baseline is the real fetched values, not {}.
  useEffect(() => {
    if (configQuery.data && !thresholdsInitialized) {
      form.reset({
        sample_id: form.getValues("sample_id"),
        thresholds: buildThresholdDefaults(configQuery.data),
      })
      setThresholdsInitialized(true)
    }
  }, [configQuery.data, thresholdsInitialized, form])

  // Live sample-id preview from the dropped filename(s), mirroring the
  // backend's own default (app/naming.py) -- stops once the analyst types
  // over it themselves.
  useEffect(() => {
    if (sampleIdEdited) return
    const filenames = [files.forward?.name, files.reverse?.name].filter(
      (name): name is string => Boolean(name)
    )
    if (filenames.length === 0) return
    form.setValue("sample_id", deriveDefaultSampleId(filenames))
  }, [files, sampleIdEdited, form])

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      // Only fields the analyst actually edited become overrides -- an
      // untouched threshold is left out entirely, never resent at its
      // current value (DESIGN.md's New Analysis section).
      const dirtyThresholds = form.formState.dirtyFields.thresholds ?? {}
      const overrides: Record<string, number> = {}
      for (const item of configQuery.data ?? []) {
        const fieldName = toFieldName(item.key)
        if (dirtyThresholds[fieldName]) {
          overrides[item.key] = values.thresholds[fieldName]
        }
      }

      const run = await createRun({
        sample_id: values.sample_id,
        forward_read: files.forward ?? undefined,
        reverse_read: files.reverse ?? undefined,
        config_overrides: overrides,
      })
      // Synchronous: this response already reflects wherever the pipeline
      // stopped, including a biological QC failure -- not an HTTP error.
      return executeRun(run.id)
    },
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] })
      navigate(`/runs/${detail.id}`)
    },
  })

  function onSubmit(values: FormValues) {
    if (!files.forward && !files.reverse) {
      setFileError("At least one AB1 file is required (forward and/or reverse).")
      return
    }
    setFileError(null)
    mutation.mutate(values)
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">New Analysis</h1>
        <p className="text-muted-foreground text-sm">
          Upload one or two AB1 reads to start a new identification run.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6">
          {mutation.isError && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertTitle>Couldn't start this run</AlertTitle>
              <AlertDescription>
                {getErrorMessage(mutation.error, "Something went wrong. Please try again.")}
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Upload</CardTitle>
              <CardDescription>
                A single read is a complete, valid analysis on its own -- not a fallback.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <DualFileDropzone files={files} onChange={setFiles} onRejected={setFileError} />
              {fileError && <p className="text-destructive text-sm">{fileError}</p>}
            </CardContent>
          </Card>

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

          {configQuery.data && (
            <ConfigOverridesSection items={configQuery.data} control={form.control} />
          )}

          <Button type="submit" disabled={mutation.isPending} className="self-start">
            {mutation.isPending ? "Running pipeline..." : "Start Analysis"}
          </Button>
        </form>
      </Form>
    </div>
  )
}
