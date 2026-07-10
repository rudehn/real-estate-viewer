// Base path for API calls. Defaults to the same-origin "/api" prefix, which
// Next.js proxies to the backend (see next.config.mjs rewrites). Can be set to
// an absolute URL (e.g. http://localhost:8000) for local dev that hits the
// backend directly. Baking a host is NOT required for the production image.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function buildUrl(path: string): URL {
  const target = `${API_BASE}${path}`;
  // Absolute base: use as-is. Relative base: resolve against the current origin
  // in the browser (or a dummy origin during SSR) so `new URL` never throws.
  if (/^https?:\/\//i.test(API_BASE)) {
    return new URL(target);
  }
  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
  return new URL(target, origin);
}

export type ParamValue = string | number | boolean | string[] | number[] | undefined | null;

export async function apiFetch<T>(
  path: string,
  params?: Record<string, ParamValue>
): Promise<T> {
  const url = buildUrl(path);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      // FastAPI expects repeated keys for list params: ?parcel_class__in=A&parcel_class__in=B
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, String(v)));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status} for ${path}`);
  }
  return res.json() as Promise<T>;
}
