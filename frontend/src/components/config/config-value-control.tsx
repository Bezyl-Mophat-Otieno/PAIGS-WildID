import { useQuery } from "@tanstack/react-query"
import { listReferenceDatabaseVersions } from "@/api/reference-database"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ConfigItem } from "@/types/api"

interface BlastModeToggleProps {
  readonly value: string
  readonly onChange: (value: string) => void
  readonly onBlur?: () => void
}

// blast.mode's own dedicated control, not the generic enum Select below --
// CLAUDE.md's remote-vs-local BLAST search decision calls for a toggle an
// analyst can't miss, with "local" only ever selectable once a reference
// database actually exists to search against (app.reference.publish's own
// active-version pointer -- reused here via the same
// ["reference-database", "versions"] query key the Reference Database page
// already populates, so this rarely needs its own network round trip).
function BlastModeToggle({ value, onChange, onBlur }: BlastModeToggleProps) {
  const { data: versions, isLoading } = useQuery({
    queryKey: ["reference-database", "versions"],
    queryFn: listReferenceDatabaseVersions,
  })
  const hasActiveLocalDb = (versions ?? []).some((v) => v.is_active)
  const localDisabled = isLoading || !hasActiveLocalDb

  return (
    <Tabs value={value} onValueChange={onChange}>
      <TabsList onBlur={onBlur}>
        <TabsTrigger value="remote">Remote</TabsTrigger>
        <Tooltip>
          <TooltipTrigger asChild>
            {/* A disabled Radix trigger drops pointer-events, which would
                also swallow the hover that shows this tooltip -- wrapping it
                in a plain, always-hoverable span keeps the explanation
                reachable exactly when it's needed. */}
            <span tabIndex={localDisabled ? 0 : -1} className="inline-flex">
              <TabsTrigger value="local" disabled={localDisabled}>
                Local
              </TabsTrigger>
            </span>
          </TooltipTrigger>
          {!isLoading && (
            <TooltipContent className="max-w-64">
              {hasActiveLocalDb
                ? "Search this deployment's own curated reference database instead."
                : "No reference database has been published yet -- publish one from the Reference Database page to enable this."}
            </TooltipContent>
          )}
        </Tooltip>
      </TabsList>
    </Tabs>
  )
}

interface ConfigValueControlProps {
  readonly item: ConfigItem
  readonly value: number | string
  readonly onChange: (value: number | string) => void
  readonly onBlur?: () => void
}

// The one place that renders a config entry's actual input control, shared
// by the global Configuration page and the per-run override section (New
// Analysis, Rerun) -- so blast.mode's toggle and the reference-DB gating it
// needs exist in exactly one place, not duplicated across screens.
export function ConfigValueControl({ item, value, onChange, onBlur }: ConfigValueControlProps) {
  if (item.key === "blast.mode") {
    return <BlastModeToggle value={value as string} onChange={onChange} onBlur={onBlur} />
  }

  if (item.value_type === "enum") {
    return (
      <Select value={value as string} onValueChange={onChange}>
        <SelectTrigger className="w-full" onBlur={onBlur}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(item.choices ?? []).map((choice) => (
            <SelectItem key={choice} value={choice}>
              {choice}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (item.value_type === "string") {
    return (
      <Input
        type="text"
        value={value as string}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder="(none)"
      />
    )
  }

  return (
    <Input
      type="number"
      step={item.value_type === "int" ? 1 : "any"}
      value={value as number}
      onChange={(e) => onChange(e.target.valueAsNumber)}
      onBlur={onBlur}
    />
  )
}
