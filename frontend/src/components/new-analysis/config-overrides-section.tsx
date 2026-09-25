import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { useFormState, type Control, type FieldValues, type Path } from "react-hook-form"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ThresholdField } from "@/components/new-analysis/threshold-field"
import { groupConfigByStage, toFieldName } from "@/lib/config-groups"
import { cn } from "cn"
import type { ConfigItem } from "@/types/api"

interface ConfigOverridesSectionProps<
  TFieldValues extends FieldValues & { thresholds: Record<string, number> },
> {
  readonly items: ConfigItem[]
  readonly control: Control<TFieldValues>
}

export function ConfigOverridesSection<
  TFieldValues extends FieldValues & { thresholds: Record<string, number> },
>({ items, control }: ConfigOverridesSectionProps<TFieldValues>) {
  const [open, setOpen] = useState(false)
  const groups = groupConfigByStage(items)

  // Visible whether or not the section is expanded -- so it's clear a real,
  // fetched default set is already in effect even before anyone opens this,
  // not just once they've gone looking for it.
  const { dirtyFields } = useFormState({ control })
  const dirtyThresholds = (dirtyFields as { thresholds?: Record<string, boolean> }).thresholds
  const modifiedCount = Object.keys(dirtyThresholds ?? {}).length
  const summary =
    modifiedCount === 0
      ? `Using ${items.length} default thresholds`
      : `${modifiedCount} of ${items.length} thresholds modified`

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="border-border rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium">
        <span>
          Thresholds
          <span className="text-muted-foreground block text-xs font-normal">{summary}</span>
        </span>
        <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-border border-t px-4 py-2">
        <Accordion type="multiple" className="w-full">
          {groups.map((group) => (
            <AccordionItem key={group.stage} value={group.stage}>
              <AccordionTrigger>{group.label}</AccordionTrigger>
              <AccordionContent className="flex flex-col gap-4 pt-1 pb-4">
                {group.items.map((item) => (
                  <ThresholdField
                    key={item.key}
                    item={item}
                    control={control}
                    name={`thresholds.${toFieldName(item.key)}` as Path<TFieldValues>}
                  />
                ))}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CollapsibleContent>
    </Collapsible>
  )
}
