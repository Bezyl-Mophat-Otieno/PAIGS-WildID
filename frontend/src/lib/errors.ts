import axios from "axios"

// Most validation failures across this API come back as `{ detail: string }`
// rather than FastAPI's default per-field array shape -- but a Pydantic
// field_validator (e.g. POST /admin/invite's email shape check) falls
// through to that default instead: `{ detail: [{ msg, loc, type }, ...] }`.
// Handle both rather than assuming every endpoint uses the string form.
export function getErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
      return detail[0].msg
    }
  }
  return fallback
}
