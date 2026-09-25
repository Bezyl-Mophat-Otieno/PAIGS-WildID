import { useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileText, Upload } from "lucide-react"
import { useDropzone } from "react-dropzone"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"
import { publishReferenceDatabase } from "@/api/reference-database"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
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
import { getErrorMessage } from "@/lib/errors"

const FASTA_EXTENSIONS = /\.(fasta|fa|fna)$/i

const formSchema = z.object({
  version: z.string().min(1, "Version label is required"),
})

type FormValues = z.infer<typeof formSchema>

export function PublishVersionDialog() {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { version: "" },
  })

  const dropzone = useDropzone({
    multiple: false,
    maxFiles: 1,
    validator: (candidate) =>
      FASTA_EXTENSIONS.test(candidate.name)
        ? null
        : { code: "file-invalid-type", message: "Only .fasta, .fa, or .fna files are accepted." },
    onDrop: (accepted, rejected) => {
      if (rejected.length > 0) {
        setFileError(rejected[0].errors[0]?.message ?? "File rejected.")
        return
      }
      setFileError(null)
      setFile(accepted[0] ?? null)
    },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      if (!file) throw new Error("A FASTA file is required.")
      return publishReferenceDatabase(file, values.version)
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["reference-database", "versions"] })
      toast.success(`Published reference database ${result.version} -- now active.`)
      setOpen(false)
      form.reset({ version: "" })
      setFile(null)
    },
  })

  function onSubmit(values: FormValues) {
    if (!file) {
      setFileError("A FASTA file is required.")
      return
    }
    mutation.mutate(values)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (mutation.isPending) return
        setOpen(next)
        if (!next) {
          form.reset({ version: "" })
          setFile(null)
          setFileError(null)
          mutation.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Upload className="size-4" />
          Publish New Version
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish reference database version</DialogTitle>
          <DialogDescription>
            Publishing immediately replaces the active reference database used for every future
            BLAST search. There's no staging step -- this takes effect right away.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
            {mutation.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {getErrorMessage(mutation.error, "Couldn't publish this version.")}
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
                    <Input placeholder="e.g. v3" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">FASTA file</span>
              {file ? (
                <div className="border-border bg-card flex items-center gap-3 rounded-lg border p-3">
                  <FileText className="text-primary size-5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{file.name}</p>
                    <p className="text-muted-foreground text-xs">
                      {(file.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setFile(null)}
                  >
                    Replace
                  </Button>
                </div>
              ) : (
                <div
                  {...dropzone.getRootProps()}
                  className={cn(
                    "border-border text-muted-foreground flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed p-6 text-center text-sm transition-colors",
                    dropzone.isDragActive && "border-primary bg-accent"
                  )}
                >
                  <input {...dropzone.getInputProps()} />
                  <Upload className="size-5" />
                  <span>Drop a .fasta/.fa/.fna file, or click to browse</span>
                </div>
              )}
              {fileError && <p className="text-destructive text-sm">{fileError}</p>}
            </div>

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
