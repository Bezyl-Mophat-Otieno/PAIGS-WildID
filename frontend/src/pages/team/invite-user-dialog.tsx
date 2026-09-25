import { useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, Copy, UserPlus } from "lucide-react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { inviteUser, type InviteResponse } from "@/api/admin"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { getErrorMessage } from "@/lib/errors"
import type { Role } from "@/types/api"

const formSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  role: z.enum(["analyst", "admin"]),
})

type FormValues = z.infer<typeof formSchema>

export function InviteUserDialog() {
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<InviteResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const queryClient = useQueryClient()

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { email: "", role: "analyst" },
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => inviteUser(values.email, values.role as Role),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] })
      setResult(data)
    },
  })

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) {
      form.reset({ email: "", role: "analyst" })
      setResult(null)
      setCopied(false)
      mutation.reset()
    }
  }

  async function copyPassword() {
    if (!result) return
    await navigator.clipboard.writeText(result.temporary_password)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <UserPlus className="size-4" />
          Invite User
        </Button>
      </DialogTrigger>
      <DialogContent>
        {result ? (
          <>
            <DialogHeader>
              <DialogTitle>Invite sent</DialogTitle>
              <DialogDescription>
                Email delivery is stubbed -- share this temporary password with{" "}
                <span className="font-medium">{result.user.email}</span> yourself. It won't be
                shown again.
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <Input readOnly value={result.temporary_password} className="font-mono" />
              <Button type="button" variant="outline" size="icon" onClick={copyPassword}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
              className="flex flex-col gap-4"
            >
              <DialogHeader>
                <DialogTitle>Invite a user</DialogTitle>
                <DialogDescription>
                  Accounts are invite-only -- this creates their login and a one-time password for
                  you to share.
                </DialogDescription>
              </DialogHeader>

              {mutation.isError && (
                <Alert variant="destructive">
                  <AlertDescription>
                    {getErrorMessage(mutation.error, "Couldn't send this invite.")}
                  </AlertDescription>
                </Alert>
              )}

              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="analyst">Analyst</SelectItem>
                        <SelectItem value="admin">Admin</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? "Sending..." : "Send Invite"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  )
}
