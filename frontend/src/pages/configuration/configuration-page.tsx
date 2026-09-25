import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Info } from "lucide-react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { listConfig, updateConfig } from "@/api/config"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Form, FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useAuth } from "@/context/auth-context"
import { groupConfigByStage, toFieldName } from "@/lib/config-groups"
import { getErrorMessage } from "@/lib/errors"
import type { ConfigItem } from "@/types/api"

type FormValues = { thresholds: Record<string, number> }

function buildDefaults(items: ConfigItem[]): Record<string, number> {
  return Object.fromEntries(items.map((item) => [toFieldName(item.key), item.value]))
}

export function ConfigurationPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === "admin"
  const queryClient = useQueryClient()

  const configQuery = useQuery({ queryKey: ["config"], queryFn: listConfig })
  const [initialized, setInitialized] = useState(false)

  const form = useForm<FormValues>({ defaultValues: { thresholds: {} } })

  useEffect(() => {
    if (configQuery.data && !initialized) {
      form.reset({ thresholds: buildDefaults(configQuery.data) })
      setInitialized(true)
    }
  }, [configQuery.data, initialized, form])

  const saveMutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const dirty = form.formState.dirtyFields.thresholds ?? {}
      const changed = (configQuery.data ?? []).filter((item) => dirty[toFieldName(item.key)])
      const results = await Promise.allSettled(
        changed.map((item) => updateConfig(item.id, values.thresholds[toFieldName(item.key)]))
      )
      return { changed, results }
    },
    onSuccess: ({ changed, results }) => {
      const updated = new Map<string, ConfigItem>()
      const failures: string[] = []
      results.forEach((result, i) => {
        if (result.status === "fulfilled") {
          updated.set(changed[i].id, result.value)
        } else {
          failures.push(`${changed[i].label}: ${getErrorMessage(result.reason, "failed to save")}`)
        }
      })

      const merged = (configQuery.data ?? []).map((item) => updated.get(item.id) ?? item)
      queryClient.setQueryData(["config"], merged)
      form.reset({ thresholds: buildDefaults(merged) })

      if (failures.length === 0) {
        toast.success(`Saved ${updated.size} threshold${updated.size === 1 ? "" : "s"}.`)
      } else {
        toast.error(`${failures.length} threshold(s) couldn't be saved: ${failures.join("; ")}`)
      }
    },
    onError: (error) => toast.error(getErrorMessage(error, "Couldn't save configuration.")),
  })

  const dirtyCount = Object.keys(form.formState.dirtyFields.thresholds ?? {}).length
  const groups = configQuery.data ? groupConfigByStage(configQuery.data) : []

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Configuration</h1>
        <p className="text-muted-foreground text-sm">
          {isAdmin
            ? "Global defaults every future run inherits, unless overridden per run."
            : "Global defaults every future run inherits. Only an admin can change these."}
        </p>
      </div>

      {configQuery.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => saveMutation.mutate(values))}
            className="flex flex-col gap-4"
          >
            <Accordion type="multiple" className="border-border rounded-lg border px-4">
              {groups.map((group) => (
                <AccordionItem key={group.stage} value={group.stage}>
                  <AccordionTrigger>{group.label}</AccordionTrigger>
                  <AccordionContent className="flex flex-col gap-4 pt-1 pb-4">
                    {group.items.map((item) => (
                      <div key={item.key} className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1.5 text-sm font-medium">
                            {item.label}
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="text-muted-foreground size-3.5" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-64">{item.description}</TooltipContent>
                            </Tooltip>
                          </span>
                          <span className="text-muted-foreground text-xs">
                            Updated {new Date(item.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                        {isAdmin ? (
                          <FormField
                            control={form.control}
                            name={`thresholds.${toFieldName(item.key)}`}
                            render={({ field, fieldState }) => (
                              <FormItem>
                                <div className="flex items-center gap-2">
                                  <FormControl>
                                    <Input
                                      type="number"
                                      step={item.value_type === "int" ? 1 : "any"}
                                      value={field.value as number}
                                      onChange={(e) => field.onChange(e.target.valueAsNumber)}
                                      onBlur={field.onBlur}
                                    />
                                  </FormControl>
                                  {fieldState.isDirty && <Badge variant="secondary">Modified</Badge>}
                                </div>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        ) : (
                          <span className="text-sm">{item.value}</span>
                        )}
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>

            {isAdmin && (
              <Button type="submit" disabled={dirtyCount === 0 || saveMutation.isPending} className="self-start">
                {saveMutation.isPending
                  ? "Saving..."
                  : dirtyCount === 0
                    ? "No changes to save"
                    : `Save ${dirtyCount} change${dirtyCount === 1 ? "" : "s"}`}
              </Button>
            )}
          </form>
        </Form>
      )}
    </div>
  )
}
