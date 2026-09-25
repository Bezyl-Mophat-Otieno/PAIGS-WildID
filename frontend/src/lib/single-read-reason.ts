const COPY: Record<string, string> = {
  single_file_provided: "Only one AB1 file was uploaded for this run -- a deliberate single-read analysis.",
  qc_failure: "One read failed the coarse sanity check; the run proceeds on the surviving read alone.",
}

export function describeSingleReadReason(reason: string | null | undefined) {
  if (!reason) return undefined
  return COPY[reason] ?? reason
}
