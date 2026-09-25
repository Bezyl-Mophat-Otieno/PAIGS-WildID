import axios from "axios"

// Every validation failure from POST /runs and PUT /config/{id} comes back
// as `{ detail: string }`, not FastAPI's default per-field array shape --
// confirmed against the actual error paths in app/api/runs.py and
// app/configuration/errors.py.
export function getErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string") return detail
  }
  return fallback
}
