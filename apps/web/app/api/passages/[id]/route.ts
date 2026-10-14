import { errorResponse, forward } from "../../../../lib/proxy";

export const dynamic = "force-dynamic";

// GET /v1/passages/{id} on the core service. The id holds "/" and ":", so the client sends it
// URL-encoded as one segment; it is read from the raw path and encoded again, whole.
export function GET(request: Request): Promise<Response> {
  const raw = new URL(request.url).pathname.split("/").pop() ?? "";
  let id: string;
  try {
    id = decodeURIComponent(raw);
  } catch {
    return Promise.resolve(errorResponse(422, "validation_error", "errors.validation"));
  }
  return forward("CORE_URL", `/v1/passages/${encodeURIComponent(id)}`, { method: "GET" }, 10_000);
}
