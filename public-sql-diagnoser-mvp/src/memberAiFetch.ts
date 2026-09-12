// One ID per logical request; duplicate transport submissions cannot spend twice.
export async function memberAiFetch(url: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  const id = crypto.randomUUID();
  headers.set("X-Request-Id", id);
  const cancel = () => { void fetch("/api/credits/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }), keepalive: true }).finally(() => window.dispatchEvent(new Event("sql-ai-complete"))).catch(() => undefined); };
  if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  init.signal?.addEventListener("abort", cancel, { once: true });
  try {
    const response = await fetch(url, { ...init, headers });
    if (response.status === 401) window.dispatchEvent(new Event("sql-login-required"));
    return response;
  } finally { init.signal?.removeEventListener("abort", cancel); window.dispatchEvent(new Event("sql-ai-complete")); }
}
