import { forward } from "../../../lib/proxy";

export const dynamic = "force-dynamic";

// GET /v1/passages?unit=<unit> on the core service. Only `unit` is passed on.
export function GET(request: Request): Promise<Response> {
  const unit = new URL(request.url).searchParams.get("unit") ?? "";
  return forward("CORE_URL", `/v1/passages?unit=${encodeURIComponent(unit)}`, { method: "GET" }, 10_000);
}
