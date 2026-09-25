import { useCallback } from "react"
import { type FileRejection, useDropzone } from "react-dropzone"
import { ArrowLeftRight, FileText, Plus, UploadCloud, X } from "lucide-react"
import { cn } from "cn"
import { Button } from "@/components/ui/button"

export type ReadSlot = "forward" | "reverse"
export type SlotFiles = Record<ReadSlot, File | null>

const SLOT_LABEL: Record<ReadSlot, string> = {
  forward: "Forward Read",
  reverse: "Reverse Read",
}

const AB1_EXTENSION = /\.ab1$/i

function ab1Validator(file: File) {
  if (!AB1_EXTENSION.test(file.name)) {
    return { code: "file-invalid-type", message: "Only .ab1 files are accepted." }
  }
  return null
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

interface DualFileDropzoneProps {
  readonly files: SlotFiles
  readonly onChange: (next: SlotFiles) => void
  readonly onRejected?: (message: string) => void
}

export function DualFileDropzone({ files, onChange, onRejected }: DualFileDropzoneProps) {
  const emptySlots = (Object.keys(SLOT_LABEL) as ReadSlot[]).filter((slot) => !files[slot])

  const handleRejections = useCallback(
    (rejections: FileRejection[]) => {
      if (rejections.length === 0) return
      const first = rejections[0]
      onRejected?.(first.errors[0]?.message ?? `"${first.file.name}" was rejected.`)
    },
    [onRejected]
  )

  // Fills empty slots in drop order (forward first, then reverse) --
  // matches DESIGN.md's "resolve into two labeled slots in drop order."
  const assignToEmptySlots = useCallback(
    (accepted: File[]) => {
      const next = { ...files }
      let cursor = 0
      for (const slot of Object.keys(SLOT_LABEL) as ReadSlot[]) {
        if (!next[slot] && cursor < accepted.length) {
          next[slot] = accepted[cursor]
          cursor += 1
        }
      }
      onChange(next)
    },
    [files, onChange]
  )

  const primary = useDropzone({
    multiple: true,
    maxFiles: 2,
    validator: ab1Validator,
    onDrop: (accepted, rejected) => {
      handleRejections(rejected)
      if (accepted.length > 0) assignToEmptySlots(accepted)
    },
  })

  function removeSlot(slot: ReadSlot) {
    onChange({ ...files, [slot]: null })
  }

  function swapSlots() {
    onChange({ forward: files.reverse, reverse: files.forward })
  }

  const bothEmpty = emptySlots.length === 2

  return (
    <div className="flex flex-col gap-3">
      {bothEmpty ? (
        <div
          {...primary.getRootProps()}
          className={cn(
            "border-border flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
            primary.isDragActive && "border-primary bg-accent"
          )}
        >
          <input {...primary.getInputProps()} />
          <UploadCloud className="text-muted-foreground size-8" />
          <p className="text-sm font-medium">Drop 1 or 2 AB1 files here, or click to browse</p>
          <p className="text-muted-foreground text-xs">
            A single read is a complete, valid analysis on its own.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {(Object.keys(SLOT_LABEL) as ReadSlot[]).map((slot) =>
            files[slot] ? (
              <FilledSlot
                key={slot}
                slot={slot}
                file={files[slot]!}
                canSwap={emptySlots.length === 0}
                onRemove={() => removeSlot(slot)}
                onSwap={swapSlots}
              />
            ) : (
              <EmptySlot
                key={slot}
                slot={slot}
                onFile={(file) => onChange({ ...files, [slot]: file })}
                onRejected={onRejected}
              />
            )
          )}
        </div>
      )}
      <p className="text-muted-foreground text-xs">
        Forward/Reverse labels are a starting guess -- the system detects true orientation
        automatically and will flag it if your labels don't match, without blocking the run.
      </p>
    </div>
  )
}

function FilledSlot({
  slot,
  file,
  canSwap,
  onRemove,
  onSwap,
}: {
  readonly slot: ReadSlot
  readonly file: File
  readonly canSwap: boolean
  readonly onRemove: () => void
  readonly onSwap: () => void
}) {
  return (
    <div className="border-border bg-card flex items-center gap-3 rounded-lg border p-3">
      <FileText className="text-primary size-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground text-xs font-medium">{SLOT_LABEL[slot]}</p>
        <p className="truncate text-sm">{file.name}</p>
        <p className="text-muted-foreground text-xs">{formatBytes(file.size)}</p>
      </div>
      {canSwap && (
        <Button variant="ghost" size="icon" type="button" aria-label="Swap reads" onClick={onSwap}>
          <ArrowLeftRight className="size-4" />
        </Button>
      )}
      <Button variant="ghost" size="icon" type="button" aria-label="Remove file" onClick={onRemove}>
        <X className="size-4" />
      </Button>
    </div>
  )
}

function EmptySlot({
  slot,
  onFile,
  onRejected,
}: {
  readonly slot: ReadSlot
  readonly onFile: (file: File) => void
  readonly onRejected?: (message: string) => void
}) {
  const dropzone = useDropzone({
    multiple: false,
    maxFiles: 1,
    validator: ab1Validator,
    onDrop: (accepted, rejected) => {
      if (rejected.length > 0) {
        onRejected?.(rejected[0].errors[0]?.message ?? "File rejected.")
        return
      }
      if (accepted[0]) onFile(accepted[0])
    },
  })

  return (
    <div
      {...dropzone.getRootProps()}
      className={cn(
        "border-border text-muted-foreground flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-3 text-center text-sm transition-colors",
        dropzone.isDragActive && "border-primary bg-accent"
      )}
    >
      <input {...dropzone.getInputProps()} />
      <Plus className="size-4" />
      <span>Add {SLOT_LABEL[slot].toLowerCase()} (optional)</span>
    </div>
  )
}
