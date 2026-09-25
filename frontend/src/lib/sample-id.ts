// Mirrors app/naming.py's default_sample_id for a live preview in the form
// -- "_".join([*stems, utc_timestamp]) with the timestamp as
// strftime("%Y%m%dT%H%M%SZ"). The backend is authoritative and re-derives
// this itself if sample_id is left blank on submit; this is only for
// showing the analyst what they'll get before they type over it.
export function deriveDefaultSampleId(filenames: string[]) {
  const stems = filenames.map((name) => name.replace(/\.[^./]+$/, ""))
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  const timestamp =
    `${now.getUTCFullYear()}${pad(now.getUTCMonth() + 1)}${pad(now.getUTCDate())}` +
    `T${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}Z`

  return [...stems, timestamp].join("_")
}
