export type QuotaNamespace = {
  idFromName(name: string): unknown;
  get(id: unknown): { fetch(request: Request): Promise<Response> };
};

type QuotaStorage = {
  sql: { exec<T>(query: string, ...params: (string | number)[]): { toArray(): T[] } };
  transactionSync<T>(callback: () => T): T;
};

export const quotaDay = (now = Date.now()) => new Date(now + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);

// One durable object per account serializes the daily allowance across sessions.
export class DemoAiQuota {
  constructor(private ctx: { storage: QuotaStorage }) {
    ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS quota (id INTEGER PRIMARY KEY, day TEXT NOT NULL, used INTEGER NOT NULL)");
  }

  async fetch(request: Request): Promise<Response> {
    const consume = request.method === "POST";
    const day = quotaDay();
    const result = this.ctx.storage.transactionSync(() => {
      const row = this.ctx.storage.sql.exec<{ day: string; used: number }>("SELECT day, used FROM quota WHERE id = 1").toArray()[0];
      let used = row?.day === day ? row.used : 0;
      const allowed = used < 10;
      if (consume && allowed) {
        used++;
        this.ctx.storage.sql.exec("INSERT INTO quota (id, day, used) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET day = excluded.day, used = excluded.used", day, used);
      }
      return { allowed, used, remaining: 10 - used, limit: 10, day, timezone: "Asia/Seoul" };
    });
    return Response.json(result, { status: consume && !result.allowed ? 429 : 200 });
  }
}

export const requestQuota = async (namespace: QuotaNamespace | undefined, username: string, consume: boolean) => {
  if (!namespace) throw new Error("Quota storage unavailable");
  const response = await namespace.get(namespace.idFromName(username)).fetch(new Request("https://quota.internal/", { method: consume ? "POST" : "GET" }));
  if (response.status !== 200 && response.status !== 429) throw new Error("Quota storage unavailable");
  return { status: response.status, quota: await response.json() };
};
