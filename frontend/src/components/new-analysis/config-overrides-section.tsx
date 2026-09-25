import { useState } from "react"
import { ChevronDown } from "lucide-react"
import type { Control, FieldValues, Path } from "react-hook-form"
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

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="border-border rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium">
        Advanced -- Threshold Overrides
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
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
