import { Info, RotateCcw } from "lucide-react"
import type { Control, FieldValues, Path } from "react-hook-form"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ConfigItem } from "@/types/api"

interface ThresholdFieldProps<TFieldValues extends FieldValues> {
  readonly item: ConfigItem
  readonly control: Control<TFieldValues>
  readonly name: Path<TFieldValues>
}

export function ThresholdField<TFieldValues extends FieldValues>({
  item,
  control,
  name,
}: ThresholdFieldProps<TFieldValues>) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <FormItem>
          <div className="flex items-center justify-between gap-2">
            <FormLabel className="flex items-center gap-1.5">
              {item.label}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="text-muted-foreground size-3.5" />
                </TooltipTrigger>
                <TooltipContent className="max-w-64">{item.description}</TooltipContent>
              </Tooltip>
            </FormLabel>
            {fieldState.isDirty && (
              <div className="flex items-center gap-1">
                <Badge variant="secondary">Modified</Badge>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-6"
                  aria-label={`Reset ${item.label} to default`}
                  onClick={() => field.onChange(item.value)}
                >
                  <RotateCcw className="size-3.5" />
                </Button>
              </div>
            )}
          </div>
          <FormControl>
            <Input
              type="number"
              step={item.value_type === "int" ? 1 : "any"}
              value={field.value as number}
              onChange={(e) => field.onChange(e.target.valueAsNumber)}
              onBlur={field.onBlur}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}
